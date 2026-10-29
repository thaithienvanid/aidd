// aidd's plugin for OpenCode V2 (the server half of the terminal surface): a no-op, and deliberately one.
// The guard, the prompt hook, and the loop hooks live in `.opencode/plugins/aidd.js` beside this directory, and
// `tui.tsx` here is the half OpenCode's terminal loads. This file only keeps the directory a plugin OpenCode discovers,
// since OpenCode loads a terminal plugin from a plugin directory, not from a bare file. It imports nothing, so nothing
// here can fail to load.
export default {
  id: "aidd-tui",
  setup() {},
}
