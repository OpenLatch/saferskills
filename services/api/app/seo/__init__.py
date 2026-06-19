"""SEO / crawl-discovery surface — sitemap generation + IndexNow submission.

This package is read-only over the public catalog: it enumerates ONLY
`visibility='public'` + completed rows, excludes the bulk auto-scan firehose
(`app.scan.constants.FEED_EXCLUDED_SOURCES`), and never emits a `share_token`
URL. See `.claude/rules/security.md` § Public-input handling.
"""
