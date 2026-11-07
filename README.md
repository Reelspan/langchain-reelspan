# langchain-reelspan

[LangChain](https://python.langchain.com) and LangGraph tools for [Reelspan](https://reelspan.com). Let an agent
publish videos, photos and text to TikTok, YouTube, Instagram, Facebook, X, Threads, LinkedIn, Pinterest, Bluesky,
Reddit and more, schedule them, check each network's result and read analytics.

```bash
pip install langchain-reelspan
export REELSPAN_API_KEY=rs_live_...   # dashboard → Developers → API keys
```

```python
from langchain.agents import create_agent
from langchain_reelspan import ReelspanToolkit

tools = ReelspanToolkit(profile="acme").get_tools()
agent = create_agent("anthropic:claude-sonnet-5-5", tools)

agent.invoke({"messages": [{"role": "user", "content":
    "Post https://cdn.example.com/launch.mp4 to TikTok and YouTube tomorrow 9am Berlin time with a short caption."}]})
```

## Tools

| Tool | |
|---|---|
| `reelspan_list_profiles` | Profiles (brands) and their connected networks |
| `reelspan_publish_video` | A video from a URL (Drive/Dropbox links work), a local path or a library media id |
| `reelspan_publish_photos` | One photo or a carousel, with alt text |
| `reelspan_publish_text` | Text; long text becomes a thread on X and Bluesky |
| `reelspan_post_status` | Each network's result |
| `reelspan_retry_post` | Send the failed networks again |
| `reelspan_post_history` | Recent posts |
| `reelspan_scheduled_posts`, `reelspan_cancel_scheduled_post` | The schedule |
| `reelspan_analytics`, `reelspan_post_analytics`, `reelspan_best_times` | Analytics |

Publishing tools take `scheduled_date` + `timezone`, `add_to_queue`, `first_comment` and `settings` for network
options (`{"privacy_level": "PUBLIC_TO_EVERYONE", "reddit_subreddit": "videos"}`; Upload-Post field names work too).

## Options

```python
from reelspan import Reelspan

ReelspanToolkit(
    client=Reelspan(api_key="rs_live_..."),  # default: reads REELSPAN_API_KEY
    profile="acme",                # pin to one profile; the model can't post as another
    platforms=["linkedin", "x"],   # only these networks
    read_only=True,                # only tools that read
    wait=True,                     # wait for each network's result after posting (default)
)
```

Single tools work too: `ReelspanPublishText(profile="acme").invoke({"platforms": ["x"], "caption": "Hi"})`.

Errors (a wrong key, a network that isn't allowed, a missing profile) come back to the model as tool messages it can
act on. Posts carry an idempotency key, so a retried call never double-posts.

## Links

[API reference](https://reelspan.com/docs) · [Python SDK](https://github.com/Reelspan/reelspan-python) ·
[MCP server](https://github.com/Reelspan/reelspan-mcp)

MIT licensed. Security reports: see [SECURITY.md](SECURITY.md).
