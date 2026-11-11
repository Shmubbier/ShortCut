// Bench-only Remotion config (pass with --config=src/video/bench3d/remotion.config.ts).
// manifold-3d's loader has a Node-only branch (`await import("node:module")`) that webpack can't bundle; stub it out.
import { Config } from '@remotion/cli/config'

Config.overrideWebpackConfig((c) => ({
  ...c,
  resolve: { ...c.resolve, fallback: { ...c.resolve?.fallback, module: false } },
  plugins: [
    ...(c.plugins ?? []),
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    new (require('webpack').NormalModuleReplacementPlugin)(/^node:/, (r: { request: string }) => { r.request = r.request.replace(/^node:/, '') }),
  ],
}))
