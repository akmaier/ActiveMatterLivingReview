source "https://rubygems.org"

# GitHub Pages pins Jekyll to a known-good set via the `github-pages` gem.
# Pinning here keeps `bundle exec jekyll serve` locally in sync with what
# GitHub Pages will build on push.
gem "github-pages", group: :jekyll_plugins

group :jekyll_plugins do
  gem "jekyll-feed"
  gem "jekyll-seo-tag"
  gem "jekyll-sitemap"
  gem "jekyll-redirect-from"
end

# Windows / JRuby fillers kept harmless on macOS.
platforms :mingw, :x64_mingw, :mswin, :jruby do
  gem "tzinfo", "~> 1.2"
  gem "tzinfo-data"
end
