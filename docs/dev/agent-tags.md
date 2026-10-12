# Tag của agent (0.100.0)

Agent được phân loại bằng **nhiều tag** thay cho một nhóm. Quyết định của chủ dự án: "Tag thực sự: mỗi agent gắn được nhiều tag, nhóm cũ chuyển thành một tag."

**Chỉ agent đổi.** Workflow và skill giữ trường `group` và hợp đồng hiện có. Nhóm Zalo, nhóm chat của team và đội làm/review của Cộng hưởng là ba khái niệm khác, không liên quan tới tag:
- **Tag** chỉ để phân loại và tìm agent (Marketing, Viết nội dung, Kỹ thuật).
- **Nhóm chat** là nơi người dùng và nhiều agent trò chuyện. Gắn tag không thêm ai vào nhóm chat.
- **Đội thực hiện** (Cộng hưởng A5, đang thiết kế) là maker và reviewer của một mục tiêu. Tag không chọn reviewer, không cấp quyền, không bật Cộng hưởng, không đổi hạn mức, không mở lượt model.

## Hợp đồng dữ liệu

### Frontmatter của `agents/<slug>.md`

```yaml
tags:
- Marketing
- Viết nội dung
```

- `tags` là **nguồn chuẩn** khi khoá này có mặt, kể cả `tags: []` (người dùng đã bỏ hết tag).
- File cũ **chưa có khoá `tags`**: đọc `group` thật trong frontmatter. `group` là chuỗi không rỗng thì thành đúng một tag (`group: Chung` thật thì thành tag "Chung"). Không có `group` hay `group` rỗng thì chưa có tag. Không suy ra tag từ nhãn "Chung" mà API cũ tự điền.
- `tags` là chuỗi đơn (người hay model ghi tay `tags: Marketing`) thì đọc thành một tag. Phần tử không phải chuỗi, rỗng sau chuẩn hoá thì bỏ qua khi đọc.
- **Gương `group`** (để hạ phiên bản vẫn có nhãn): mỗi lần ghi chuẩn, `group` = tag đầu tiên; không còn tag thì xoá khoá `group`. Khi đã có `tags`, mã 0.100.0 trở đi KHÔNG đọc `group` của agent.
- Ghi bằng `yaml.safe_dump` như mọi frontmatter khác, đọc bằng `fastyaml.safe_load`: danh sách ra danh sách, chuỗi có ký tự đặc biệt được trích dẫn.

### Chuẩn hoá và trùng

- Unicode NFC; bỏ ký tự điều khiển; gộp mọi khoảng trắng liên tiếp thành một dấu cách; cắt hai đầu.
- Rỗng sau chuẩn hoá: không phải tag.
- **Giới hạn chỉ cho đầu vào MỚI** (review vòng 1, R1): tag người dùng thêm, thay cả tập hay đổi tên tới dài quá 40 ký tự thì từ chối (`tag_too_long`); thêm làm tập vượt 20 tag thì từ chối (`too_many_tags`).
- **Dữ liệu ĐANG CÓ không bao giờ bị cắt:** nhóm cũ dài hơn 40 ký tự (hợp lệ ở 0.96.1) hay file có hơn 20 tag được đọc nguyên, hiện nguyên (chip cắt chữ bằng CSS, tên đủ ở title), và ghim, lưu form, nhập gói ghi lại đúng như đã đọc. Bỏ, đổi tên (tên nguồn) hay xoá một tag dài vẫn làm được; bỏ tag khi đang quá 20 luôn được.
- **Khoá định danh** = dạng chuẩn hoá rồi Unicode `casefold()` (`agent_tags.tag_key`): "Marketing" và "marketing" là một tag; "Straße" và "STRASSE" là một tag; "Viết" dạng NFC và NFD là một tag. Dấu tiếng Việt là một phần của tag: "Viết" và "Viet" là hai tag khác nhau. Tìm kiếm không dấu chỉ để tìm, không gộp tag. Trong một agent giữ cách viết gặp trước; giữa các agent, cách viết có thể khác nhau nhưng cùng khoá.
- **Một định danh cho mọi tầng** (R3): API trả `tag_keys` song song với `tags`; trang Cộng sự và Studio đếm, lọc, đánh dấu tick theo khoá đó, không tự tính (`toLowerCase` của trình duyệt khác `casefold`). Giao diện chỉ hiển thị cách viết server trả về.

### API

| Đường | Agent | Ghi chú |
|---|---|---|
| `GET /agents`, `GET /agents/get` | Trả `tags` (danh sách đã chuẩn hoá) và `tag_keys` (khoá định danh, cùng thứ tự) | Vẫn trả `group` = tag đầu tiên hoặc "Chung" cho trang cũ còn trong cache. Không gửi một request riêng cho từng agent |
| `POST /capability/meta`, `kind=agent` | `add_tags` (JSON danh sách): thêm vào tập hiện có. `remove_tags` (JSON danh sách): bỏ đúng các tag đó. `tags` (JSON danh sách): thay cả tập, `[]` là bỏ hết | Không gửi trường nào = giữ nguyên. Đọc và ghi trong một bước của server, nên hai tab thêm/bỏ khác tag không ghi đè nhau |
| `POST /capability/meta`, `kind=agent`, chỉ có `group` (client cũ) | Agent đang có từ hai tag trở lên: từ chối `409 stale_client` ("Trang đã cũ, tải lại trang"), không đổi gì. Có không quá một tag: `group` không rỗng thành đúng một tag, rỗng là bỏ tag (đúng nghĩa cũ "về Chưa xếp nhóm") | Không bao giờ âm thầm thay nhiều tag bằng một tag |
| `group` gửi cùng `tags`/`add_tags`/`remove_tags` | Từ chối `400 group_and_tags` | Luật xung đột rõ, không đoán |
| `POST /agents` (form sửa agent) | Không gửi `tags` = giữ nguyên tag. Gửi `tags` (JSON) = thay cả tập. `group` của client cũ theo đúng luật hàng trên | Agent mới không gửi tag thì `tags: []` |
| `POST /agents/tags/rename` (`brain`, `from_tag`, `to_tag`) | Đổi tên tag (so theo khoá) trên mọi agent đang có nó, giữ các tag khác. `to_tag` trùng khoá với một tag đã có thì gộp, không nhân đôi, dùng cách viết của tag đã có | Trả `changed`, `failed`, `merged`, `tag`, `tag_key`. Có agent ghi lỗi thì `ok: false` kèm danh sách đã làm và chưa làm |
| `POST /agents/tags/delete` (`brain`, `tag`) | Gỡ nhãn đó khỏi mọi agent | Không xoá agent, phiên chat, mục tiêu hay đội. Trả như trên |
| `kind=workflow` | Không đổi; gửi tham số tag cho workflow bị từ chối `400` | |

Mọi tag thuộc phạm vi **một brain** (thư mục `agents/` của brain đó). Đổi tên hay xoá tag ở brain này không chạm brain khác.

**Đồng bộ ghi và event loop** (R4, R5): mọi đường đọc, sửa, ghi hay XOÁ file agent chạy ở worker (`asyncio.to_thread`) và đi tuần tự qua CÙNG một khoá (`_AGENT_META_LOCK`):
- `/capability/meta` (agent), đổi tên tag, xoá tag, `POST /agents` của form, sáu route tài liệu/link của agent (`/agents/{slug}/assets/...`), và `POST /agents/delete`.
- Đọc `previous`, kiểm file còn tồn tại, rồi ghi, đều nằm trong khoá. Đợi khoá cũng ở worker, nên thao tác nhiều agent hay xoá đang đợi khoá không chặn event loop khi đĩa chậm.
- Form lưu xen với thêm/bỏ tag không ghi đè nhau.
- **Xoá agent không bị hoàn tác** (R5): thao tác ghi đang giữ khoá thì xoá đợi nó ghi xong rồi mới xoá. Thao tác tới sau lúc xoá thấy file đã mất và không tạo lại: `/capability/meta` và route tài liệu trả 404; đổi tên hay xoá tag hàng loạt bỏ qua agent đó (không vào `changed`, không vào `failed`).
- `POST /agents` (form) vẫn là tạo-hoặc-sửa như trước: lưu form sau khi agent đã bị xoá là tạo một agent MỚI cùng tên, không mang tag hay vai cũ, và theo luật A1 phải bật lại Cộng hưởng.
- Workflow giữ nguyên như trước 0.100.0: `/capability/meta` cho workflow sửa ngay trên event loop như các route workflow khác (lưu, bật/tắt, xoá), không qua worker hay khoá này.

Số đo trong test là I/O giả lập (ghi chậm 80 ms, barrier giữ worker), không phải số đo máy thật.

## Chuyển đổi

- **Đọc tương thích, ghi chuẩn khi lưu.** Không có migration hàng loạt và không quét ghi lại file khi tải danh sách.
- Một agent cũ được ghi sang dạng chuẩn (`tags` + gương `group`) ở lần đầu có thao tác lưu chạm vào nó: Lưu form, ghim, gắn hay bỏ tag, đổi tên hay xoá tag. Ghi chuẩn hai lần cho cùng kết quả (lặp an toàn): tag đã có `tags` thì đọc `tags`, không đọc lại `group`.
- Mọi khoá frontmatter khác và thân prompt giữ nguyên (đọc rồi chỉ sửa khoá tag). Ghi nguyên tử bằng `_atomic_write_text`.

## Nhập, xuất, chỉ mục, tạo từ chat

- **Xuất** chép nguyên file agent: gói mới mang `tags`.
- **Nhập** ghi nguyên file: gói mới giữ đủ tag; gói cũ chỉ có `group` thì được đọc thành đúng một tag theo luật file cũ, và thành dạng chuẩn ở lần lưu đầu.
- **Chỉ mục** `Javis/index.md`: agent liệt kê một lần mỗi agent, kèm "tags: A, B"; workflow và skill vẫn chia theo nhóm.
- **Tạo agent từ chat** (`javis-builder`, `CLAUDE.md`): mẫu agent dùng `tags:` (danh sách), đọc các tag đang dùng trong `agents/*.md` trước khi chọn.

## Quay về

- **Hạ về 0.96.1 (mã cũ):** mã cũ đọc `group`, nên agent hiện dưới nhóm = tag đầu tiên (gương), agent không còn tag hiện là "Chung". Khoá `tags` còn nguyên trong file, mã cũ giữ nó khi lưu (đã giữ mọi khoá lạ từ 0.59.x). Đã kiểm trên trình duyệt với `main` 0.96.1 mở bản sao dữ liệu đã chuyển.
- **Giới hạn:** file agent có `tags` mà chưa từng được mã 0.100.0 lưu (người hay model ghi tay chỉ `tags`, hay gói nhập từ nơi khác) thì chưa có gương `group`, nên mã cũ hiện nó là "Chung" cho tới khi được lưu một lần bằng mã mới. Không mất tag.
- **Nâng lại 0.100.0:** `tags` là nguồn chuẩn. Thay đổi nhóm làm bằng mã cũ trong lúc hạ phiên bản (sửa `group`) **không** được đưa vào tag; muốn giữ thì gắn lại tag. Đây là giới hạn đã biết, đổi lại tag đã bỏ không bao giờ sống lại từ `group`.
- Không có bản sao file riêng: chuyển đổi chỉ thêm khoá `tags` và đồng bộ `group`, không xoá nội dung nào.
