// Static console served by the FastAPI app. Astro hashes every bundled script and style into the
// CSP meta tag, so pages never use inline style attributes; every page talks only to its own origin.
import { defineConfig } from 'astro/config';

export default defineConfig({
  output: 'static',
  build: { format: 'file', inlineStylesheets: 'always' },
  markdown: { syntaxHighlight: false },
  security: {
    csp: {
      directives: [
        "default-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "base-uri 'none'",
        "form-action 'self'",
        "object-src 'none'",
      ],
    },
  },
});
