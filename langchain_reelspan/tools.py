"""LangChain tools for Reelspan, built on the official ``reelspan`` client."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional, Sequence, Type

from langchain_core.tools import BaseTool, ToolException
from pydantic import BaseModel, ConfigDict, Field
from reelspan import Reelspan, ReelspanError

PLATFORMS = (
    "tiktok", "youtube", "instagram", "facebook", "x", "threads", "linkedin", "pinterest", "bluesky", "reddit",
    "google_business", "telegram", "discord", "slack", "mastodon", "devto", "hashnode",
    "wordpress", "sandbox",
)


def _compact(value: Any, depth: int = 0) -> Any:
    """Drops nulls and raw network payloads so answers stay small for the model."""
    if isinstance(value, list):
        return [_compact(v, depth + 1) for v in value[:100]]
    if isinstance(value, dict):
        return {k: ("…" if depth > 6 else _compact(v, depth + 1)) for k, v in value.items() if v is not None and k not in ("raw", "usage")}
    return value


class _ReelspanTool(BaseTool):
    """Shared settings: the client, a pinned profile, allowed networks, and waiting for results."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    client: Reelspan = Field(default_factory=Reelspan, exclude=True)
    profile: Optional[str] = None
    """Pins the tool to one profile: the model can't post as another."""
    allowed_platforms: Optional[List[str]] = None
    wait: bool = True
    """Wait for each network's result after posting."""
    wait_timeout: float = 300.0
    handle_tool_error: bool = True

    def _who(self, profile: Optional[str]) -> str:
        who = self.profile or profile
        if not who:
            raise ToolException("Which profile? Call reelspan_list_profiles and pass its username as profile.")
        return who

    def _check_platforms(self, platforms: Sequence[str]) -> List[str]:
        if not platforms:
            raise ToolException("Give at least one network in platforms.")
        allowed = self.allowed_platforms or PLATFORMS
        bad = [p for p in platforms if p not in allowed]
        if bad:
            raise ToolException(f"Not allowed: {', '.join(bad)}. Allowed networks: {', '.join(allowed)}.")
        return list(platforms)

    def _call(self, fn: Any, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        try:
            return _compact(fn(*args, **kwargs))
        except ReelspanError as e:
            hint = " (the API key is invalid)" if e.status == 401 else " (check the profile or id)" if e.status == 404 else ""
            raise ToolException(f"Reelspan {e.status}{' ' + e.code if e.code else ''}: {e}{hint}") from e

    def _finish(self, r: Dict[str, Any]) -> Dict[str, Any]:
        if self.wait and r.get("request_id") and not r.get("job_id") and not r.get("results"):
            done = self._call(self.client.posts.wait, r["request_id"], timeout=self.wait_timeout)
            return {"request_id": r["request_id"], **done}
        return r


# ─── inputs ─────────────────────────────────────────────────────────────────────────────────────────


class _PostInput(BaseModel):
    platforms: List[str] = Field(description=f"Networks to post to: {', '.join(PLATFORMS)}")
    profile: Optional[str] = Field(default=None, description="The profile username (from reelspan_list_profiles)")
    caption: Optional[str] = Field(default=None, description="Caption, post text or YouTube title")
    description: Optional[str] = Field(default=None, description="Longer description where the network has one")
    scheduled_date: Optional[str] = Field(default=None, description="Publish later: ISO-8601 date-time; leave out to post now")
    timezone: Optional[str] = Field(default=None, description="IANA timezone for scheduled_date, e.g. Europe/Berlin")
    add_to_queue: bool = Field(default=False, description="Take the profile's next free queue slot")
    first_comment: Optional[str] = None
    settings: Optional[Dict[str, Any]] = Field(default=None, description='Network settings, e.g. {"privacy_level": "PUBLIC_TO_EVERYONE", "reddit_subreddit": "videos"}')

    def common(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "scheduled_date": self.scheduled_date,
            "timezone": self.timezone,
            "add_to_queue": self.add_to_queue,
            "first_comment": self.first_comment,
            "extra": self.settings,
            "async_upload": True,
        }


class VideoInput(_PostInput):
    video: Optional[str] = Field(default=None, description="Public https URL of the video (Drive and Dropbox links work) or a local file path")
    media_id: Optional[str] = Field(default=None, description="A library media id instead")


class PhotosInput(_PostInput):
    photos: List[str] = Field(default_factory=list, description="Public URLs or local paths, in carousel order")
    media_ids: Optional[List[str]] = None
    alt_texts: Optional[List[str]] = Field(default=None, description="Alt text per photo, in order")


class TextInput(_PostInput):
    caption: str = Field(description="The post text. Long text becomes a thread on X and Bluesky.")


class StatusInput(BaseModel):
    request_id: Optional[str] = None
    job_id: Optional[str] = Field(default=None, description="For a scheduled post")


class RetryInput(BaseModel):
    request_id: str
    platforms: Optional[List[str]] = Field(default=None, description="Only these; default every failed network")


class HistoryInput(BaseModel):
    profile: Optional[str] = None
    platform: Optional[str] = None
    status: Optional[Literal["success", "failed"]] = None
    limit: Literal[10, 20, 50] = 20


class ProfileInput(BaseModel):
    profile: Optional[str] = Field(default=None, description="The profile username")


class AnalyticsInput(ProfileInput):
    days: Optional[int] = Field(default=None, description="Day-by-day history of this many days")


class JobInput(BaseModel):
    job_id: str


class RequestInput(BaseModel):
    request_id: str


class EmptyInput(BaseModel):
    pass


# ─── tools ──────────────────────────────────────────────────────────────────────────────────────────


class ReelspanListProfiles(_ReelspanTool):
    name: str = "reelspan_list_profiles"
    description: str = "List Reelspan profiles (brands) and the networks each has connected. Call this first to find the profile username."
    args_schema: Type[BaseModel] = EmptyInput

    def _run(self, **_: Any) -> Any:
        r = self._call(self.client.profiles.list)
        rows = [{"username": p["username"], "name": p.get("display_name"), "networks": [k for k, v in (p.get("social_accounts") or {}).items() if v]} for p in r.get("profiles", [])]
        return [p for p in rows if p["username"] == self.profile] if self.profile else rows


class ReelspanPublishVideo(_ReelspanTool):
    name: str = "reelspan_publish_video"
    description: str = "Publish (or schedule) a video to one or more social networks."
    args_schema: Type[BaseModel] = VideoInput

    def _run(self, platforms: List[str], profile: Optional[str] = None, caption: Optional[str] = None, video: Optional[str] = None, media_id: Optional[str] = None, **kw: Any) -> Any:
        if not video and not media_id:
            raise ToolException("Give video (a URL or path) or media_id.")
        i = VideoInput(platforms=platforms, **kw)
        return self._finish(self._call(self.client.posts.video, self._who(profile), self._check_platforms(platforms), video, caption, video_media_id=media_id, **i.common()))


class ReelspanPublishPhotos(_ReelspanTool):
    name: str = "reelspan_publish_photos"
    description: str = "Publish (or schedule) one photo or a carousel to one or more social networks."
    args_schema: Type[BaseModel] = PhotosInput

    def _run(self, platforms: List[str], profile: Optional[str] = None, caption: Optional[str] = None, photos: Optional[List[str]] = None, media_ids: Optional[List[str]] = None, alt_texts: Optional[List[str]] = None, **kw: Any) -> Any:
        if not photos and not media_ids:
            raise ToolException("Give photos (URLs or paths) or media_ids.")
        i = PhotosInput(platforms=platforms, **kw)
        return self._finish(self._call(self.client.posts.photos, self._who(profile), self._check_platforms(platforms), photos or (), caption, photo_media_ids=media_ids, alt_texts=alt_texts, **i.common()))


class ReelspanPublishText(_ReelspanTool):
    name: str = "reelspan_publish_text"
    description: str = "Publish (or schedule) a text post to one or more social networks (X, Threads, LinkedIn, Bluesky, Facebook, Mastodon, Discord, Telegram…)."
    args_schema: Type[BaseModel] = TextInput

    def _run(self, platforms: List[str], caption: str, profile: Optional[str] = None, **kw: Any) -> Any:
        i = TextInput(platforms=platforms, caption=caption, **kw)
        return self._finish(self._call(self.client.posts.text, self._who(profile), self._check_platforms(platforms), caption, **i.common()))


class ReelspanPostStatus(_ReelspanTool):
    name: str = "reelspan_post_status"
    description: str = "Each network's result for a post, by request_id (or job_id for a scheduled post)."
    args_schema: Type[BaseModel] = StatusInput

    def _run(self, request_id: Optional[str] = None, job_id: Optional[str] = None, **_: Any) -> Any:
        if not request_id and not job_id:
            raise ToolException("Give request_id or job_id.")
        return self._call(self.client.posts.status, request_id=request_id, job_id=job_id)


class ReelspanRetryPost(_ReelspanTool):
    name: str = "reelspan_retry_post"
    description: str = "Send the networks that failed again, with the media Reelspan already has."
    args_schema: Type[BaseModel] = RetryInput

    def _run(self, request_id: str, platforms: Optional[List[str]] = None, **_: Any) -> Any:
        return self._call(self.client.posts.retry, request_id, platforms=platforms)


class ReelspanPostHistory(_ReelspanTool):
    name: str = "reelspan_post_history"
    description: str = "Recent posts, one row per network, newest first."
    args_schema: Type[BaseModel] = HistoryInput

    def _run(self, profile: Optional[str] = None, platform: Optional[str] = None, status: Optional[str] = None, limit: int = 20, **_: Any) -> Any:
        query = {k: v for k, v in {"profile_username": self.profile or profile, "platform": platform, "status": status, "limit": limit}.items() if v}
        return self._call(self.client.posts.history, **query).get("history", [])


class ReelspanScheduledPosts(_ReelspanTool):
    name: str = "reelspan_scheduled_posts"
    description: str = "Posts waiting for their scheduled time."
    args_schema: Type[BaseModel] = ProfileInput

    def _run(self, profile: Optional[str] = None, **_: Any) -> Any:
        who = self.profile or profile
        return self._call(self.client.scheduled.list, **({"profile_username": who} if who else {}))


class ReelspanCancelScheduledPost(_ReelspanTool):
    name: str = "reelspan_cancel_scheduled_post"
    description: str = "Cancel a scheduled post so it is never published."
    args_schema: Type[BaseModel] = JobInput

    def _run(self, job_id: str, **_: Any) -> Any:
        return self._call(self.client.scheduled.cancel, job_id)


class ReelspanAnalytics(_ReelspanTool):
    name: str = "reelspan_analytics"
    description: str = "Followers, reach and engagement of a profile per network; with days, a day-by-day history."
    args_schema: Type[BaseModel] = AnalyticsInput

    def _run(self, profile: Optional[str] = None, days: Optional[int] = None, **_: Any) -> Any:
        who = self._who(profile)
        return self._call(self.client.analytics.history, who, days=days) if days else self._call(self.client.analytics.account, who)


class ReelspanPostAnalytics(_ReelspanTool):
    name: str = "reelspan_post_analytics"
    description: str = "Views, likes, comments and shares of one post, by request_id."
    args_schema: Type[BaseModel] = RequestInput

    def _run(self, request_id: str, **_: Any) -> Any:
        return self._call(self.client.analytics.post, request_id)


class ReelspanBestTimes(_ReelspanTool):
    name: str = "reelspan_best_times"
    description: str = "The best hours to post for a profile, from its own past engagement."
    args_schema: Type[BaseModel] = ProfileInput

    def _run(self, profile: Optional[str] = None, **_: Any) -> Any:
        return self._call(self.client.analytics.best_times, self._who(profile))


WRITE_TOOLS = (ReelspanPublishVideo, ReelspanPublishPhotos, ReelspanPublishText, ReelspanRetryPost, ReelspanCancelScheduledPost)
READ_TOOLS = (ReelspanListProfiles, ReelspanPostStatus, ReelspanPostHistory, ReelspanScheduledPosts, ReelspanAnalytics, ReelspanPostAnalytics, ReelspanBestTimes)


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
