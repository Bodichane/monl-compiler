"""Ambiance décorative partagée par toutes les pages de la plateforme."""

CSS = """
/* ---------- ambiance partagée ---------- */
.site-ambient { position:fixed; inset:68px 0 0; z-index:0; overflow:hidden;
  pointer-events:none; contain:strict; opacity:.72; }
.ambient-grid { position:absolute; inset:0;
  background-image:linear-gradient(color-mix(in srgb,var(--line) 28%,transparent) 1px,transparent 1px),linear-gradient(90deg,color-mix(in srgb,var(--line) 28%,transparent) 1px,transparent 1px);
  background-size:72px 72px; mask-image:linear-gradient(to bottom,black,transparent 88%); }
.ambient-orbit { position:absolute; aspect-ratio:1; border:1px dashed color-mix(in srgb,var(--line-strong) 48%,transparent);
  border-radius:50%; will-change:transform; animation:ambient-turn 42s linear infinite; }
.ambient-orbit-a { width:min(46vw,660px); right:-220px; top:-180px; }
.ambient-orbit-b { width:min(34vw,480px); left:-190px; top:44%; animation-duration:56s; animation-direction:reverse; }
.ambient-orbit::before,.ambient-orbit::after,.ambient-orbit i { content:""; position:absolute; border-radius:50%; }
.ambient-orbit::before { width:34%; aspect-ratio:1; inset:33%; border:1px solid color-mix(in srgb,var(--line) 54%,transparent); }
.ambient-orbit::after { width:10px; height:10px; left:12%; top:18%; background:var(--accent);
  box-shadow:0 0 0 8px color-mix(in srgb,var(--accent) 9%,transparent); }
.ambient-orbit i { width:7px; height:7px; background:var(--brand); }
.ambient-orbit i:nth-child(1) { right:8%; top:42%; }
.ambient-orbit i:nth-child(2) { left:31%; bottom:3%; background:var(--accent); }
.ambient-orbit i:nth-child(3) { left:2%; top:54%; }
.ambient-beam { position:absolute; width:min(48vw,680px); height:1px; right:8%; top:42%;
  background:linear-gradient(90deg,transparent,color-mix(in srgb,var(--accent) 42%,transparent),transparent);
  transform:rotate(-14deg); opacity:.7; }
@keyframes ambient-turn { to { transform:rotate(1turn); } }

@media (max-width: 780px) {
  .site-ambient { opacity:.48; }
  .ambient-grid { background-size:56px 56px; }
  .ambient-orbit-b { display:none; }
}
@media (prefers-reduced-motion: reduce) {
  .ambient-orbit { animation:none !important; }
}
"""
