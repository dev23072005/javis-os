"""Tag của agent (0.100.0): mỗi agent gắn nhiều tag, nhóm cũ thành một tag.

Hàm thuần, không đọc ghi file, để test được và để server, chỉ mục, giao diện hiểu tag giống nhau.
Hợp đồng đầy đủ: docs/dev/agent-tags.md.

- `tags` trong frontmatter là nguồn chuẩn khi khoá có mặt, kể cả danh sách rỗng.
- File cũ chưa có `tags`: `group` thật (chuỗi không rỗng) thành đúng một tag. Không suy từ nhãn
  "Chung" mà API cũ tự điền khi file không khai `group`.
- Chỉ áp cho AGENT. Workflow và skill vẫn dùng `group`.
"""
from __future__ import annotations

import json
import re
import unicodedata

TAG_MAX_CHARS = 40
TAGS_MAX = 20

_WS = re.compile(r"\s+")


class TagError(ValueError):
    """Mã lỗi máy (`tag_too_long`, `too_many_tags`, `bad_tags`), giao diện dịch sang câu người đọc."""


def clean_tag(value) -> str:
    """Dạng chuẩn của một tag, "" nếu không phải tag: NFC, bỏ ký tự điều khiển, gộp khoảng trắng.
    KHÔNG áp giới hạn độ dài: dùng khi ĐỌC dữ liệu đang có và khi so khoá (review PR #617 vòng 1, R1)."""
    if not isinstance(value, str):
        return ""
    s = unicodedata.normalize("NFC", value)
    s = "".join(ch for ch in s if not unicodedata.category(ch).startswith("C") or ch in "\t\n\r")
    return _WS.sub(" ", s).strip()


def normalize_tag(value) -> str:
    """Như `clean_tag`, cộng giới hạn độ dài: chỉ dùng cho tag người dùng THÊM MỚI hay đổi tên tới."""
    s = clean_tag(value)
    if len(s) > TAG_MAX_CHARS:
        raise TagError("tag_too_long")
    return s


def tag_key(value) -> str:
    """Khoá định danh của một tag, DÙNG CHUNG cho server và giao diện (API trả kèm `tag_keys`, giao diện
    không tự tính): dạng chuẩn rồi Unicode casefold ("Straße" và "STRASSE" là một tag). Giữ dấu:
    "Viết" khác "Viet". Không giới hạn độ dài, để bỏ hay đổi tên được cả tag cũ dài."""
    return clean_tag(value).casefold()


def _dedupe(values) -> list:
    out, seen = [], set()
    for v in values:
        t = clean_tag(v)
        k = t.casefold()
        if t and k not in seen:
            seen.add(k)
            out.append(t)
    return out


def read_tags(values) -> list:
    """Tag ĐANG CÓ (file, gói nhập): chuẩn hoá, bỏ trùng theo khoá, giữ cách viết gặp trước, bỏ phần tử
    không phải chuỗi hay rỗng. KHÔNG cắt theo độ dài hay số lượng: giới hạn chỉ dành cho đầu vào mới, còn
    dữ liệu đã có thì giữ nguyên để thao tác khác (ghim, lưu form) không làm mất phân loại."""
    return _dedupe(v for v in values or [] if isinstance(v, str))


def normalize_tags(values) -> list:
    """Tập tag MỚI do người dùng gửi (thay cả tập): chuẩn hoá, bỏ trùng, áp đủ giới hạn."""
    out = _dedupe(normalize_tag(v) for v in values or [])
    if len(out) > TAGS_MAX:
        raise TagError("too_many_tags")
    return out


def tags_of(meta) -> list:
    """Tag của một agent đọc từ frontmatter (luật đọc tương thích, không cắt dữ liệu đang có)."""
    meta = meta if isinstance(meta, dict) else {}
    if "tags" in meta:
        raw = meta.get("tags")
        if isinstance(raw, str):
            raw = [raw]
        elif not isinstance(raw, (list, tuple)):
            raw = []
        return read_tags(raw)
    g = meta.get("group")
    if isinstance(g, str) and g.strip():
        return read_tags([g])
    return []


def write_tags(meta: dict, tags: list) -> dict:
    """Ghi dạng chuẩn vào `meta` (sửa tại chỗ và trả lại): `tags` + gương `group` để hạ phiên bản
    vẫn có nhãn. Không còn tag thì xoá `group`, để mã cũ hiện "Chung" chứ không hiện tag đã bỏ.
    Ghi đúng tập đã cho (đã đọc hay đã kiểm ở nơi gọi), không cắt lại."""
    tags = read_tags(tags)
    meta["tags"] = list(tags)
    if tags:
        meta["group"] = tags[0]
    else:
        meta.pop("group", None)
    return meta


def parse_list(raw) -> list | None:
    """Tham số danh sách từ form: None = không gửi. Nhận JSON (danh sách chuỗi) hoặc một chuỗi đơn."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TagError("bad_tags")
    s = raw.strip()
    if not s:
        return []
    if s.startswith("["):
        try:
            v = json.loads(s)
        except ValueError as e:
            raise TagError("bad_tags") from e
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise TagError("bad_tags")
        return v
    return [s]


def apply_ops(current: list, *, replace=None, add=None, remove=None) -> list:
    """Tập tag mới: thay cả tập (nếu có), rồi thêm, rồi bỏ theo khoá. Không gửi gì thì giữ nguyên.

    Giới hạn chỉ áp cho phần MỚI: tag thay cả tập và tag thêm vào phải hợp lệ; tag đang có giữ nguyên dù
    dài hay nhiều hơn giới hạn (dữ liệu cũ). Thêm làm tập vượt `TAGS_MAX` thì từ chối; bỏ thì luôn được."""
    out = normalize_tags(replace) if replace is not None else read_tags(current)
    if add:
        co = {t.casefold() for t in out}
        moi = [t for t in _dedupe(normalize_tag(x) for x in add) if t.casefold() not in co]
        if moi and len(out) + len(moi) > TAGS_MAX:
            raise TagError("too_many_tags")
        out = out + moi
    if remove:
        bo = {k for k in (tag_key(x) for x in remove) if k}
        out = [t for t in out if t.casefold() not in bo]
    return out


def from_old_group(current: list, group: str) -> list:
    """Luật tương thích cho client cũ chỉ gửi `group` (một nhóm). Agent đang có từ hai tag trở lên
    thì từ chối (`stale_client`): thay nhiều tag bằng một là mất dữ liệu. Còn lại: nhóm không rỗng
    thành đúng một tag, rỗng là bỏ tag (nghĩa cũ "về Chưa xếp nhóm")."""
    if len(current or []) > 1:
        raise TagError("stale_client")
    g = normalize_tag(group or "")
    return [g] if g else []


def rename(current: list, src: str, dst: str) -> tuple[list, bool]:
    """Đổi tag `src` thành `dst` trên một agent, giữ các tag khác và vị trí. Trả (tập mới, có đổi).
    `src` so theo khoá (đổi được cả tag cũ dài); `dst` là tên mới nên phải hợp lệ. `dst` trùng khoá một
    tag khác của agent thì gộp, không nhân đôi."""
    ks = tag_key(src)
    d = normalize_tag(dst)
    if not ks or not d:
        raise TagError("bad_tags")
    cur = read_tags(current)
    if not any(t.casefold() == ks for t in cur):
        return cur, False
    out = _dedupe(d if t.casefold() == ks else t for t in cur)
    return out, out != cur
