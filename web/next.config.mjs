// A static export: `next build` writes plain HTML, JS and CSS to dist/, and the FastAPI app serves it,
// so the console and the API are one deployable on one origin.
export default {
  output: 'export',
  distDir: 'dist',
  reactStrictMode: true,
};
