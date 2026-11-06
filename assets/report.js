// Review sheet. Data comes from sheet.review_sheet as JSON in <script id=data>.
const DATA = JSON.parse(document.getElementById("data").textContent);
const ITEMS = DATA.items, SECTIONS = DATA.sections;
const LANES = {against: "Against the board", unclear: "Unclear", with: "With the board"};
const START = "Our starting point when deciding how to vote is to support the board.";  // verbatim from the guidelines

const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const count = lane => ITEMS.filter(r => r.lane === lane).length;
const chevron = '<svg class=chev viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>';
const copyIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>';

// Where the proposed vote stands against the board, shown next to an Unclear tag.
function side(r) {
  if (!r.board) return "";
  return r.vote === r.board ? "with" : "against";
}

function section(r) {
  return r.section && SECTIONS[r.section];
}

function basisTitle(r) {
  const s = section(r);
  const title = r.section ? `Global voting guidelines ${r.section}${s ? " " + s.heading : ""}` : "Global voting guidelines";
  return title + (r.section && !r.cited ? ", quote not verified" : "");
}

function basisText(r) {
  const s = section(r);
  return s ? s.text : START;
}

function head() {
  const n = ITEMS.length || 1;
  document.getElementById("split").innerHTML =
    ["against", "with", "unclear"].map(l => `<i class=${l}-c style="width:${count(l) / n * 100}%"></i>`).join("");
  document.getElementById("total").innerHTML = `<strong>${ITEMS.length}</strong><span>proposals</span>`;
  document.getElementById("lanes").innerHTML =
    ["against", "with", "unclear"].map(l =>
      `<div style="width:${count(l) / n * 100}%"><strong>${count(l)}</strong><span><i class="dot ${l}-c"></i>${LANES[l]}</span></div>`).join("");
}

function proposal(r) {
  let tags = `<span class="tag ${r.lane}">${LANES[r.lane]}</span>`;
  if (r.lane === "unclear" && side(r)) tags += `<span class="tag ${side(r)}">${LANES[side(r)]}</span>`;
  if (r.read_first) tags += `<span class="tag first" title="Order only. The proposed vote is unchanged.">Read first</span>`;
  // The applied rule is marked inside the full paragraph, so it is not repeated below.
  const full = basisText(r), inside = r.quote && full.includes(r.quote);
  const text = inside ? esc(full).replace(esc(r.quote), `<strong>${esc(r.quote)}</strong>`) : esc(full);
  let body = `<button class=copy type=button aria-label="Copy context for a language model">${copyIcon}<span>Copy</span></button>
    <p><b>Draft reason:</b> ${esc(r.why)}</p>`;
  body += r.section
    ? `<p><b>Basis:</b> ${esc(basisTitle(r))}</p><div class=para><button class=more type=button>Read more</button><p>${text}</p></div>`
    : `<p><b>Basis:</b> ${r.basis === START ? `Global voting guidelines: “${esc(START)}”` : esc(r.basis || START)}</p>`;
  if (r.quote && !inside) body += `<p><b>Quoted:</b> ${esc(r.quote)}</p>`;
  if (r.evidence) body += `<p><b>From the filing:</b> ${esc(r.evidence)}</p>`;
  if (r.pay) body += `<p><b>Pay facts:</b> ${esc(r.pay)}</p>`;
  if (r.check && r.lane !== "with") body += `<p><b>Check:</b> ${esc(r.check)}</p>`;
  if (r.flags) body += `<p><b>Sent to a person:</b> ${esc(r.flags)}</p>`;
  if (r.rationale && r.lane === "against") {
    const paper = r.paper ? ` <a href="${esc(r.paper[1])}">Position paper: ${esc(r.paper[0])}</a>.` : "";
    body += `<div class=rationale><p><b>Vote rationale:</b> ${esc(r.rationale)}${paper}</p></div>`;
  }
  return `<details class=prop data-lane=${r.lane} data-item="${esc(r.item)}" data-vote="${esc(r.vote)}" data-score="${r.score}">
    <summary>
      <span class=no>${esc(r.item)}</span>
      <span class=title><strong>${esc(r.text)}</strong><span class=tags>${tags}</span></span>
      <span class=cell><span class=lab>Board</span>${esc(r.board || "Not stated")}</span>
      <span class="cell vote"><span class=lab>Proposed</span>${esc(r.vote)}</span>
      <span class="cell conf"><span class=track><i style="width:${r.score}%"></i></span><span>${r.score}%</span></span>
      <span class=cell><span class=lab>Review</span>${esc(r.review)}</span>
      ${chevron}
    </summary>
    <div class=body>${body}</div>
  </details>`;
}

function context(r) {
  const lines = [
    `${DATA.company}, ${DATA.country}. General meeting ${DATA.meeting_date}.${DATA.notice ? " Not fully read: " + DATA.notice : ""}`,
    `Proposal ${r.item}: ${r.text}`,
    `Board recommends: ${r.board || "Not stated"}`,
    `Proposed vote: ${r.vote} (${LANES[r.lane]})`,
    `Confidence: ${r.score}%`,
    `Review: ${r.review}`,
    `Draft reason: ${r.why}`,
    `Basis: ${r.section ? `${basisTitle(r)}. ${basisText(r)}` : r.basis || START}`,
  ];
  if (r.quote) lines.push(`Rule quoted: ${r.quote}`);
  if (r.evidence) lines.push(`From the filing: ${r.evidence}`);
  if (r.pay) lines.push(`Pay facts: ${r.pay}`);
  if (r.check) lines.push(`Check: ${r.check}`);
  if (r.flags) lines.push(`Sent to a person: ${r.flags}`);
  if (r.rationale) lines.push(`Vote rationale: ${r.rationale}`);
  if (r.paper) lines.push(`Position paper: ${r.paper[0]}, ${r.paper[1]}`);
  return lines.join("\n");
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const t = Object.assign(document.createElement("textarea"), {value: text});
    document.body.append(t); t.select(); document.execCommand("copy"); t.remove();
  }
}

const ICONS = {
  all: '<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="3.5" cy="6" r="1"/><circle cx="3.5" cy="12" r="1"/><circle cx="3.5" cy="18" r="1"/>',
  unclear: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6"/><circle cx="12" cy="17" r=".6"/>',
  against: '<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>',
  with: '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16 9.5"/>',
};
const icon = k => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[k]}</svg>`;

function filters() {
  const box = document.getElementById("filters");
  const opts = [["all", "All"], ["unclear", LANES.unclear], ["against", LANES.against], ["with", LANES.with]];
  box.innerHTML = opts.map(([k, t], i) =>
    `<button type=button data-key=${k} aria-pressed=${i === 0}>${icon(k)}<span>${t}</span></button>`).join("");
  box.addEventListener("click", e => {
    const b = e.target.closest("button");
    if (!b) return;
    box.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", x === b));
    document.querySelectorAll(".prop").forEach(p => p.hidden = b.dataset.key !== "all" && p.dataset.lane !== b.dataset.key);
  });
}

function actions() {
  document.getElementById("list").addEventListener("click", async e => {
    const more = e.target.closest(".more");
    if (more) {
      const open = more.parentElement.classList.toggle("open");
      more.textContent = open ? "Read less" : "Read more";
      return;
    }
    const btn = e.target.closest(".copy");
    if (btn) {
      const r = ITEMS.find(x => String(x.item) === btn.closest(".prop").dataset.item);
      await copy(context(r));
      btn.querySelector("span").textContent = "Copied";
      setTimeout(() => btn.querySelector("span").textContent = "Copy", 1600);
    }
  });
  const toggle = document.getElementById("toggle");
  toggle.addEventListener("click", () => {
    const open = toggle.textContent === "Open all";
    document.querySelectorAll(".prop:not([hidden])").forEach(p => p.open = open);
    toggle.textContent = open ? "Close all" : "Open all";
  });
}

// A divider only between items on the same line.
function dividers() {
  for (const row of document.querySelectorAll(".info")) {
    let top = null;
    for (const el of row.children) {
      el.classList.remove("start");
      if (top !== null && el.offsetTop > top) el.classList.add("start");
      top = el.offsetTop;
    }
  }
}
addEventListener("resize", dividers);
document.fonts.ready.then(dividers);

// Proposals logged on this page, counted from the green dots the sign-off sets.
function reviewed() {
  document.getElementById("reviewed").innerHTML =
    `<strong>${document.querySelectorAll(".prop.approved").length}</strong><span>proposals reviewed</span>`;
}

head();
reviewed();
new MutationObserver(reviewed).observe(document.getElementById("list"), {subtree: true, attributes: true, attributeFilter: ["class"]});
dividers();
document.getElementById("list").innerHTML = ITEMS.map(proposal).join("");
filters();
actions();
