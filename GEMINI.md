<!-- graft:start -->
## Graft — repo context graph

This repo is indexed in `graft/`: small linked markdown nodes that explain each
system and carry exact file:line spans, kept in sync with the code through git.

For ANY task here — understanding how something works, finding where code lives,
or scoping a change — get context from the graph before grepping or opening
source files. Re-ask freely (it's cheap) and reuse literal identifiers you
already have (symbol, error string, file name) as the query. New to this repo?
Run `graft map` first — a token-budgeted orientation (dir clusters, hubs,
hotspots), no LLM, no key.

- Run `graft ask "<your question>" --source` → ranked nodes with the relevant
  code spans inlined (each hit's ≤8-line crux by default; `--full` for whole
  definitions when the crux isn't enough). Match the tool to the task shape:
  for understanding or editing, the top node IS the answer — cite its
  `covers:` file:line spans and edit straight from `--source`. For
  exhaustive tasks ("every occurrence / every caller of this pattern"), ranked
  results are top-N, not complete — run `graft grep "<literal>"` instead
  (exhaustive over indexed files, grouped by enclosing symbol), falling back
  to raw `grep -rn` only for unindexed files.
- `graft skeleton <file>` → every definition's signature + span, ~10× cheaper
  than reading the file; use it to skim an API surface.
- `graft callers <symbol>` gives precomputed, exact edges — who calls this.
  Add `--direction out` for what it calls, or `--depth N` to walk
  transitively for the full blast radius. For structural questions, skip
  ranking and use this directly.
- Or browse: `graft/INDEX.md` lists every node; follow the links.
- Monorepos and folders of multiple repos rank fairly across sub-projects —
  hits carry `[scope/]` labels naming which one they're from. Narrow with
  `graft ask "<task>" --in <scope>/` once you know where you're working.

If a returned span is truncated ("+N more lines"), open the file at that exact
range before finalizing. Only open source files when a node genuinely lacks a
needed detail, and then at the exact file:line the node points to — never
re-read whole files.

After big code changes, refresh the graph with `graft build` (deterministic,
no API key, $0).
<!-- graft:end -->

---

## Nhật ký Lập trình (Project Development Log)

### [2026-11-02] Tái cấu trúc trình phát Media sang kiến trúc VLC (`VLCPlayerEngine` & `PlayerFrame`) và chuẩn hóa Trợ năng (Accessibility)

#### 1. Nguyên nhân & Vấn đề đã giải quyết
- **Lỗi Player khi `yt-dlp` cập nhật**: Hàm `_get_stream_url` cũ trong `source/modules/player.py` ép cứng `--extractor-args "youtube:player_client=web,mweb,android,tv"` và `-f "b"`. Khi `yt-dlp` cập nhật (ví dụ `2026.10.26`), các client cũ bị chặn bởi GVS PO Token / SABR / EJS JS Runtime khiến cờ `-f "b"` báo lỗi `Requested format is not available`, trong khi `source/modules/downloader.py` không ép client nên vẫn hoạt động ổn định.
- **Sai đường dẫn thư viện VLC**: Code cũ tìm thư mục `vlc lib` thay vì `dll file` (trong môi trường dev) hoặc thư mục gốc (khi đóng gói bằng Nuitka).
- **Chế độ Play Audio chưa tách luồng**: Chế độ `audio_only=True` trước đây vẫn tải luồng video MP4 và hiển thị khung hình đen toàn màn hình.
- **Trợ năng (MSAA/UIA & NVDA)**: `wx.Window.GetAccessible()` trả về `None` mặc định trên Windows (`wxMSW`), khiến tên trợ năng (`SetName`) và giá trị thời gian thực của thanh trượt không được truyền sang NVDA; `Auto()` của `accessible_output2` bị khởi tạo lại liên tục trên thread phụ mỗi lần bấm phím.

#### 2. Các thay đổi kiến trúc trong `source/modules/player.py`
- **Tự động nhận diện môi trường VLC (`_setup_vlc_environment`)**: Tự động nạp `libvlc.dll`, `libvlccore.dll` và thư mục `plugins` từ `source/dll file` hoặc thư mục thực thi đóng gói.
- **Lớp `VLCStreamSource` & `_resolve_vlc_source`**:
  - Mở trực tiếp file nội bộ và luồng media thông thường bằng VLC.
  - Với link YouTube: Loại bỏ hoàn toàn `--extractor-args` và `-f "b"`, đồng bộ cơ chế lấy luồng mặc định ổn định như `downloader.py`.
  - **Play Audio (`audio_only=True`)**: Cấp trực tiếp luồng âm thanh HLS (`bestaudio[protocol*=m3u8]/bestaudio[ext=m4a]/bestaudio`) vào VLC (`--no-video`), khởi chạy tức thì và tua mượt không độ trễ.
  - **Play Video (`audio_only=False`)**: Tự động tạo HLS Master Playlist (`.m3u8` chuẩn `#EXT-X-VERSION:3`) kết hợp luồng Video H.264 (`avc1`, lên tới 720p) và luồng Audio AAC cho bộ `adaptive demux` của VLC, tự động dọn dẹp file tạm khi đóng.
- **Lớp `VLCPlayerEngine`**:
  - Quản lý độc lập vòng đời `vlc.Instance` và `vlc.MediaPlayer`, định tuyến thiết bị âm thanh đầu ra (`get_playback_device`), giải phóng danh sách thiết bị (`libvlc_audio_output_device_list_release`) và dọn file `.m3u8` tạm.
  - Hỗ trợ cộng dồn thao tác tua nhanh liên tiếp (`_last_seek_target`) giúp bấm phím mũi tên Trái/Phải nhiều lần không bị nhảy ngược về thời gian cũ khi VLC đang nạp phân đoạn HLS.
- **Lớp `ControlAccessible(wx.Accessible)` & `PlayerFrame`**:
  - Gắn `wx.Accessible` tùy chỉnh cho mọi điều khiển để cung cấp `GetName`, `GetDescription`, `GetHelpText` và `GetValue` (thanh thời gian đọc rõ `"MM:SS of MM:SS"`, thanh âm lượng đọc `"X percent"`) cho NVDA.
  - Đặt nhãn `wx.StaticText` (`&Position:`, `&Volume:`) ngay trước `wx.Slider` theo đúng thứ tự Win32/MSAA.
  - Tối ưu giao diện riêng cho chế độ `Playing Audio` (ẩn `videopanel`, cửa sổ gọn 640x280) và `Playing Video` (toàn màn hình).
  - Bổ sung nút `&Mute` / `&Unmute` (phím tắt `M`), đọc thời gian hiện tại trên tổng thời lượng (phím `T`), `Space`, `Left/Right`, `Up/Down`, `Home/End`, `Alt+K`, `Escape`, và tự động trả lại focus về cửa sổ/nút gốc khi đóng trình phát.

#### 3. Khắc phục lỗi treo tiến trình `cmd` khi thoát ứng dụng & lỗi mất Focus về `ListBox` sau khi đóng Player
- **Lỗi mất Focus (không bấm được `Tab` / mũi tên Lên/Xuống sau khi bấm `Escape` thoát Player)**:
  - **Nguyên nhân**: Khi `TeTubeFrame.play_url` mở hộp thoại modal `PlayProgressDialog`, hàm `_show_player` trước đây gọi `wx.Window.FindFocus()` ngay lúc `PlayProgressDialog` đang mở nên bắt nhầm `wx.Panel` bên trong `PlayProgressDialog`. Khi `PlayProgressDialog.Destroy()` chạy, `wx.Panel` đó bị xóa (`RuntimeError: wrapped C/C++ object of type Panel has been deleted`), khiến lúc đóng `PlayerFrame` focus bị rơi vào khung vỏ `TeTubeFrame` thay vì `wx.ListBox` (`result_list`, `favorite_list`, `history_list`).
  - **Giải pháp**:
    - Bổ sung `_get_restore_focus_target()`, `_get_active_tab_focus_target()` và `restore_list_focus()` trong `TeTubeFrame` (`source/modules/gui.py`) để ghi nhận chính xác `wx.ListBox` / điều khiển đang có focus trước khi mở `PlayProgressDialog`, truyền qua `previous_focus` tới `PlayProgressDialog` -> `play_video` -> `_show_player` -> `PlayerFrame`.
    - Trong `_on_source_ready` và `_show_player` (`source/modules/player.py`), đóng `PlayProgressDialog` hoàn tất (`IsModal() == False`) trước khi khởi tạo và hiển thị `PlayerFrame`.
    - Khi đóng `PlayerFrame` (`on_close`), thoát chế độ toàn màn hình (`ShowFullScreen(False)`), ẩn cửa sổ trước khi `Destroy()`, kích hoạt lại `TeTubeFrame` và khôi phục focus + vùng chọn (`SetSelection`) trực tiếp về `wx.ListBox` đang hoạt động.
- **Lỗi tiến trình không dừng hẳn trong `cmd` và Task Manager (`te_tube.exe`) sau khi phát video và đóng ứng dụng**:
  - **Nguyên nhân**:
    1. `TeTubeFrame.on_close` trước đây chỉ gọi `self.Destroy()` (làm cửa sổ chính biến mất) và chờ `app.MainLoop()` tự kết thúc. Khi `PlayerFrame` sử dụng subclass Python `ControlAccessible(wx.Accessible)` cùng NVDA (`nvdaHelperRemote.dll` / `oleacc.dll`), các tham chiếu COM/SIP giữ `wxPendingDelete` khiến `app.MainLoop()` không bao giờ kết thúc.
    2. Trên Windows, `os._exit(0)` gọi `ExitProcess(0)` (`ntdll!LdrShutdownProcess`), giữ **Windows Loader Lock** và gọi `DllMain(DLL_PROCESS_DETACH)` tuần tự cho toàn bộ plugin DLL của `libvlc.dll` (`direct3d11`, `mmdevice` WASAPI) và COM (`oleacc.dll`, `nvdaHelperRemote.dll`), gây deadlock ở tầng Loader Lock sau khi giao diện đã đóng.
  - **Giải pháp**:
    - Loại bỏ subclass Python `ControlAccessible(wx.Accessible)`, sử dụng `wxWindowAccessible` C++ nguyên bản của `wxMSW` (`control.SetName` + `SetHelpText`) kết hợp đọc trực tiếp qua `self.speak_text` cho NVDA.
    - Trong `VLCPlayerEngine.cleanup(fast_exit=False)`: tháo `set_hwnd(0)` trên UI thread và đẩy việc giải phóng `media_player.stop()`, `media_player.release()`, `media.release()`, `instance.release()` sang luồng `daemon=True` để không bao giờ làm nghẽn UI thread; khi thoát hẳn ứng dụng (`fast_exit=True`), xóa ngay toàn bộ file `.m3u8` tạm (`_all_temp_files`).
    - Xây dựng `_force_exit_process(0)` trong `source/modules/gui.py` gọi trực tiếp syscall `ctypes.windll.kernel32.TerminateProcess(GetCurrentProcess(), 0)` ngay bên trong `TeTubeFrame.on_close` (sau khi `self.Hide()`, dừng `clipboard_timer` và gọi `close_current_player(fast_exit=True)`), bỏ qua `LdrShutdownProcess` để chấm dứt tiến trình tức khắc (0ms) cả khi chạy `run.bat` lẫn bản đóng gói Nuitka `te_tube.exe`.


