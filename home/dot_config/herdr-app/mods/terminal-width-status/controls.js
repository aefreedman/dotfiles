import { div } from "gpui-kit";
import { h_flex, Input, InputState } from "gpui-base";
import { layout, run, shared, setShared, checking, nextCommand } from "herdr";

const KEY = "terminal-width-status.preferences";
function find(node, id) {
  if (!node) return null;
  if (node.id === id) return node;
  for (const child of node.children ?? []) {
    const result = find(child, id);
    if (result) return result;
  }
}

export class WidthControls {
  constructor(cx) {
    const saved = shared(KEY);
    // During a layout switch, layout() can still describe the previous layout.
    this.width = Number(saved?.width) || find(layout(), "main")?.max || 750;
    this.align = ["left", "center", "right"].includes(saved?.align) ? saved.align : "left";
    this.input = InputState.new({ value: String(this.width) });
    this.input.on("submit", (_, cx) => this.commit(cx));
    this.input.on("blur", (_, cx) => this.commit(cx));
    if (!checking()) cx.spawn(async (cx) => {
      for (;;) {
        const command = await nextCommand();
        if (["left", "center", "right"].includes(command)) {
          this.align = command;
          this.apply();
          cx.notify();
        } else if (command.startsWith("width:")) {
          this.input.set_value(command.slice(6));
          this.commit(cx);
        }
      }
    });
  }

  commit(cx) {
    const value = Number(this.input.value().trim());
    if (Number.isFinite(value) && value >= 240 && value <= 5000) {
      this.width = Math.round(value);
      this.apply();
    }
    this.input.set_value(String(this.width));
    cx.notify();
  }

  measure(size) {
    if (this.available === size.width || checking()) return;
    this.available = size.width;
    this.apply();
  }

  apply() {
    if (checking()) return;
    const tree = JSON.parse(JSON.stringify(layout()));
    const main = find(tree, "main");
    const before = find(tree, "terminal-space-before");
    const after = find(tree, "terminal-space-after");
    if (!main || !before || !after) return;
    const panel = find(tree, "panel");
    const panelWidth = panel && !panel.hidden ? (panel.size?.px ?? 368) + 8 : 0;
    // The status bar spans the work area; subtract the work body's padding
    // and any open side panel. Keep the cap even when the window is smaller.
    const available = Math.max(1, (this.available ?? 1441) - 16 - panelWidth);
    main.max = this.width;
    main.size = { px: Math.min(this.width, available) };
    before.hidden = this.align === "left";
    after.hidden = this.align === "right";
    const prefs = shared(KEY);
    if (prefs?.width !== this.width || prefs?.align !== this.align)
      setShared(KEY, { width: this.width, align: this.align });
    if (JSON.stringify(tree) !== JSON.stringify(layout())) run("layout.set", { layout: tree });
  }

  render(t) {
    const button = (label, action, active = false) => div().id(`width-${label}`)
      .px(6).h(22).flex().items_center().rounded(4)
      .bg(active ? t.selected : t.chrome).text_color(active ? t.foreground : t.muted)
      .hover(s => s.bg(t.hover)).on_click((_, cx) => { action(); cx.notify(); }).child(label);
    return h_flex().items_center().gap(4)
      .child("Max width")
      .child(button("−", () => { this.width = Math.max(240, this.width - 50); this.input.set_value(String(this.width)); this.apply(); }))
      .child(Input.new(this.input).w(58).h(22).px(5).text_size(12).bg(t.surface).text_color(t.foreground).border(1).border_color(t.border).rounded(4))
      .child("px")
      .child(button("+", () => { this.width = Math.min(5000, this.width + 50); this.input.set_value(String(this.width)); this.apply(); }))
      .children(["left", "center", "right"].map(align => button(align[0].toUpperCase() + align.slice(1), () => { this.align = align; this.apply(); }, this.align === align)));
  }
}
