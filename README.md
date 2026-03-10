# WordPress Poster Skill for Claude

A Claude skill for publishing and managing WordPress posts via the WordPress REST API.

## Features

- ✅ Create posts (draft / publish / pending / private)
- ✅ Update posts (title, content, status, featured image)
- ✅ List / read / delete posts
- ✅ Manage categories (list / create)
- ✅ Upload media (images, files)
- ✅ Credentials managed via `.env` — never hardcoded

## Setup

1. Copy `.env.example` to `.env` and fill in your credentials:

```dotenv
WP_URL=https://your-site.com
WP_USERNAME=your_wp_username
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
```

2. Generate an **Application Password** in WordPress:
   > Admin → Users → Profile → Application Passwords → Add New

3. Install dependencies with `uv`:

```bash
uv init my-wp-project
cd my-wp-project
uv add httpx python-dotenv
```

4. Run:

```bash
# List latest posts
uv run scripts/wp_poster.py list

# Create a draft
uv run scripts/wp_poster.py create "My New Post Title"
```

## Skill Structure

```
wordpress-poster/
├── SKILL.md              # Claude skill instructions
├── .env.example          # Environment variable template
├── README.md
└── scripts/
    └── wp_poster.py      # Core WordPress REST API helper
```

## Requirements

- Python 3.11+
- `httpx`
- `python-dotenv`
- WordPress 5.6+ with REST API enabled
- WordPress Application Password
