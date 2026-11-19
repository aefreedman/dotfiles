import { View, div } from "gpui-kit";
import { v_flex, TextView } from "gpui-base";
import { checking, props, readTextFile, theme, watchFolder } from "herdr";

export default class MarkdownViewer extends View {
  init(initial, cx) {
    this.file = props()?.file ?? initial?.file;
    this.message = "Pass an absolute path to a local .md file.";
    if (typeof this.file !== "string" ||
        !/^(?:[a-z]:[\\/]|\/(?!\/))/i.test(this.file) ||
        !/\.md$/i.test(this.file)) return;
    this.message = "Waiting for Markdown…";
    if (checking()) return;

    const dir = this.file.slice(0, Math.max(this.file.lastIndexOf("/"), this.file.lastIndexOf("\\")) + 1);
    cx.spawn(async cx => {
      try {
        for (;;) {
          // Arm before reading so a save during the read is not lost.
          const watch = watchFolder(dir);
          const changed = watch.then(() => true, () => false);
          await this.reload(cx);
          if (!(await changed)) break;
        }
      } catch {
        // A folder may not exist yet or may be unavailable to the watcher.
      }
      cx.timer.every(2000, cx => this.reload(cx));
    });
  }

  async reload(cx) {
    if (this.reading) return;
    this.reading = true;
    try {
      let body = null;
      let message = "Waiting for Markdown…";
      try {
        body = await readTextFile(this.file);
        if (body !== null && !body.trim()) message = "This Markdown file is empty.";
      } catch {
        message = "Could not read the Markdown file.";
      }
      if (body !== this.body || message !== this.message) {
        this.body = body;
        this.message = message;
        cx.notify();
      }
    } finally {
      this.reading = false;
    }
  }

  render() {
    const t = theme();
    return v_flex().size_full().bg(t.surface).text_color(t.foreground)
      .child(div().id("markdown-scroll").size_full().overflow_y_scrollbar().p(16)
        .child(this.body?.trim()
          ? TextView.markdown("markdown-document", this.body)
          : div().child(this.message)));
  }
}
