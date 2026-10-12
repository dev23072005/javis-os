/* Probe cho tests/python/test_agent_tags.py (không phải test chạy riêng): đọc danh sách agent đúng như
   GET /agents trả (stdin, JSON), chạy MÃ THẬT phần tag của trang Cộng sự (workspace.js) và trang Studio
   (studio.js), in kết quả JSON để test Python so với cách server so trùng tag.

       node tests/js/agent_tags_ui_probe.js < agents.json

   Không trình duyệt, không server, không model. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const agents = input.agents;

global.window = { t: (k) => k, ic: () => "", addEventListener() {}, removeEventListener() {},
                  matchMedia: () => ({ matches: false }) };
global.document = { getElementById: () => null,
                    createElement: () => ({ classList: { add() {}, remove() {} }, appendChild() {} }),
                    body: { classList: { add() {}, remove() {} } } };
global.localStorage = { getItem: () => null, setItem() {} };
require(path.join(ROOT, "dashboard", "workspace.js"));
const W = window.JavisWorkspace;

// Studio: bóc khối tag (từ TAG_NONE tới hết locTheoNhom) và chạy trong vm với đúng các phụ thuộc của nó.
const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "studio.js"), "utf8");
const a = SRC.indexOf('  const TAG_NONE = " none";');
const b = SRC.indexOf("  // Bấm nhóm thì vẽ lại CẢ trang");
const ctx = { NHOM_MD: "Chung", nhomCua: (x) => (x && String(x.group || "").trim()) || "Chung", LOC: () => "vi",
              t: (k) => k, esc: (s) => String(s), _spNoAccent: (s) => String(s).toLowerCase(),
              demNhom: () => ({}) };
vm.createContext(ctx);
vm.runInContext(SRC.slice(a, b) + "\nthis.__S = { demTag, locTheoNhom, tagCap };", ctx);
const S = ctx.__S;

// Bảng kết quả không có prototype: khoá là tên tag tuỳ ý ("__proto__" là tag hợp lệ).
const out = { workspace: {}, studio: {} };
// demTag ném lỗi (mã cũ gặp tag "__proto__") thì ghi lỗi vào kết quả, đếm như rỗng, chạy tiếp các phần khác.
let wd;
try { wd = W.demTag(agents); } catch (e) { out.workspace.error = e.message; wd = { tags: [], khong: 0 }; }
out.workspace.buckets = wd.tags.map((g) => ({ ten: g.ten, key: g.key, n: g.n }));
out.workspace.khong = wd.khong;
out.workspace.filter = Object.create(null);
for (const g of wd.tags) out.workspace.filter[g.key] = W.loc(agents, "", g.key, true).map((x) => x.slug).sort();
// Lọc bằng TÊN hiển thị (đúng cách trang cũ hay test cũ truyền vào) phải ra cùng kết quả với lọc bằng khoá.
out.workspace.filterByName = Object.create(null);
for (const x of agents) for (const ten of x.tags || []) out.workspace.filterByName[ten] = W.loc(agents, "", ten, true).map((y) => y.slug).sort();
// Mã cũ chưa có dongChonTag (bộ chọn dựng thẳng trong DOM): báo null, test Python tính là hỏng, không sập.
out.workspace.ticks = W.dongChonTag ? Object.create(null) : null;
if (W.dongChonTag) for (const x of agents) out.workspace.ticks[x.slug] = W.dongChonTag(x, agents).filter((r) => r.on).map((r) => r.key).sort();

const sd = S.demTag(agents);
out.studio.buckets = sd.tags.map((g) => ({ ten: g.ten, key: g.key, n: g.n }));
out.studio.filter = Object.create(null);
for (const g of sd.tags) out.studio.filter[g.key] = S.locTheoNhom(agents, { cat: g.key, q: "" }, () => "", true).map((x) => x.slug).sort();
out.prototypeClean = ({}).n === undefined && Object.prototype.n === undefined;
process.stdout.write(JSON.stringify(out));
