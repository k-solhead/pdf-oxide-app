"""
pdf-oxide-app — PDF 範囲指定テキスト抽出アプリ
参照ページを画像表示 → マウスドラッグで領域指定 → within() で絞って全ページ抽出
"""
import hashlib
import io
import os
import threading
import uuid
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from pdf_oxide import PdfDocument

st.set_page_config(page_title="PDF 範囲指定テキスト抽出", layout="wide")
st.title("📄 PDF 範囲指定テキスト抽出")
st.markdown(
    "PDF の参照ページを画像表示し、マウスドラッグで**抽出したい領域**を指定。"
    " `within()` で範囲を絞って全ページからテキストを取得します。"
)

# ── セッション状態 ──
if "bbox_pt" not in st.session_state:
    st.session_state.bbox_pt = None
if "drag_raw" not in st.session_state:
    st.session_state.drag_raw = None
if "uploaded_bytes" not in st.session_state:
    st.session_state.uploaded_bytes = None
if "uploaded_name" not in st.session_state:
    st.session_state.uploaded_name = None
if "uploaded_hash" not in st.session_state:
    st.session_state.uploaded_hash = None
if "drag_clear_nonce" not in st.session_state:
    st.session_state.drag_clear_nonce = 0
if "drag_session_id" not in st.session_state:
    st.session_state.drag_session_id = uuid.uuid4().hex


COMP_DIR = Path("/tmp/pdf_oxide_drag_component")
IMAGES_DIR = COMP_DIR / "images"
IMAGE_SERVER_PORT_ENV = "PDF_OXIDE_IMAGE_SERVER_PORT"
_image_server = None
_image_server_lock = threading.Lock()


class _QuietImageHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        return


@st.cache_resource
def get_image_server():
    global _image_server
    with _image_server_lock:
        if _image_server is not None:
            return _image_server

        COMP_DIR.mkdir(parents=True, exist_ok=True)
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)

        try:
            port = int(os.getenv(IMAGE_SERVER_PORT_ENV, "8765"))
        except ValueError as exc:
            raise RuntimeError(f"{IMAGE_SERVER_PORT_ENV} は整数で指定してください。") from exc

        handler = partial(_QuietImageHandler, directory=str(IMAGES_DIR))
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        except OSError as exc:
            raise RuntimeError(
                f"画像配信用ポート {port} を使用できません。"
                f"環境変数 {IMAGE_SERVER_PORT_ENV} で空きポートを指定してください。"
            ) from exc

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        _image_server = {"port": port, "images_dir": IMAGES_DIR, "server": server}
        return _image_server


@st.cache_resource
def drag_component():
    COMP_DIR.mkdir(parents=True, exist_ok=True)
    index = COMP_DIR / "index.html"
    if not index.exists():
        index.write_text(
            """<!DOCTYPE html>
<html>
<head>
  <meta charset=\"UTF-8\" />
</head>
<body style=\"margin:0;padding:0;background:#1e1e1e;text-align:center;\">
  <div id=\"wrap\" style=\"position:relative;display:inline-block;width:100%;\">
    <img id=\"P\" style=\"display:block;width:100%;height:auto;cursor:crosshair;\" crossorigin=\"anonymous\" />
    <canvas id=\"C\" style=\"position:absolute;left:0;top:0;width:100%;height:100%;cursor:crosshair;\"></canvas>
  </div>
<script>
(function(){
  const wrap = document.getElementById('wrap');
  const I = document.getElementById('P');
  const C = document.getElementById('C');
  const ctx = C.getContext('2d');

  let NW = 1, NH = 1;
  let dragging = false;
  let start = null;
  let selection = null;
  let currentImage = null;
  let currentClearNonce = null;
  let currentMaxW = 960;

  function sendMessage(type, data) {
    window.parent.postMessage(
      Object.assign({ isStreamlitMessage: true, type: type }, data || {}),
      '*'
    );
  }

  function setComponentValue(value) {
    sendMessage('streamlit:setComponentValue', { value: value });
  }

  function setFrameHeight(height) {
    sendMessage('streamlit:setFrameHeight', { height: height });
  }

  function setComponentReady() {
    sendMessage('streamlit:componentReady', { apiVersion: 1 });
  }

  function toCanvas(p){
    return { x: (p.x / NW) * C.width, y: (p.y / NH) * C.height };
  }

  function toImageCoords(e){
    const r = I.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(NW, ((e.clientX - r.left) / r.width) * NW)),
      y: Math.max(0, Math.min(NH, ((e.clientY - r.top) / r.height) * NH)),
    };
  }

  function draw(){
    ctx.clearRect(0, 0, C.width, C.height);
    const target = dragging && start ? { x1: start.x, y1: start.y, x2: selection.x2, y2: selection.y2 } : selection;
    if (!target) return;
    const p1 = toCanvas({x: target.x1, y: target.y1});
    const p2 = toCanvas({x: target.x2, y: target.y2});
    const x = Math.min(p1.x, p2.x);
    const y = Math.min(p1.y, p2.y);
    const w = Math.abs(p2.x - p1.x);
    const h = Math.abs(p2.y - p1.y);
    ctx.strokeStyle = '#00ff88';
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(x, y, w, h);
    ctx.setLineDash([]);
    ctx.fillStyle = 'rgba(0,255,136,0.15)';
    ctx.fillRect(x, y, w, h);
  }

  function resize(){
    const r = I.getBoundingClientRect();
    if (!r.width || !r.height) return;
    C.width = r.width;
    C.height = r.height;
    draw();
    setFrameHeight(Math.ceil(r.height) + 24);
  }

  C.addEventListener('mousedown', (e) => {
    const p = toImageCoords(e);
    dragging = true;
    start = p;
    selection = { x1: p.x, y1: p.y, x2: p.x, y2: p.y };
    draw();
  });

  C.addEventListener('mousemove', (e) => {
    if (!dragging || !start) return;
    const p = toImageCoords(e);
    selection = { x1: start.x, y1: start.y, x2: p.x, y2: p.y };
    draw();
  });

  window.addEventListener('mouseup', (e) => {
    if (!dragging || !start) return;
    dragging = false;
    const p = toImageCoords(e);
    const x1 = Math.min(start.x, p.x);
    const y1 = Math.min(start.y, p.y);
    const x2 = Math.max(start.x, p.x);
    const y2 = Math.max(start.y, p.y);
    selection = { x1, y1, x2, y2 };
    draw();

    if ((x2 - x1) < 10 || (y2 - y1) < 10) return;

    setComponentValue({
      ix1: x1,
      iy1: y1,
      ix2: x2,
      iy2: y2,
    });
  });

  window.addEventListener('resize', resize);

  function onRender(event) {
    if (!event.data || event.data.type !== 'streamlit:render') return;
    const args = event.data.args || {};

    NW = Number(args.nw || 1);
    NH = Number(args.nh || 1);
    currentMaxW = Number(args.max_w || 960);
    wrap.style.maxWidth = `${currentMaxW}px`;

    if (args.img_url && args.img_url !== currentImage) {
      currentImage = args.img_url;
      I.src = args.img_url;
      I.onerror = function() {
        console.error('Failed to load image:', args.img_url);
      };
    }

    if (args.clear_nonce !== currentClearNonce) {
      currentClearNonce = args.clear_nonce;
      selection = null;
      start = null;
    }

    if (!selection && args.initial_coords) {
      selection = {
        x1: Number(args.initial_coords.ix1),
        y1: Number(args.initial_coords.iy1),
        x2: Number(args.initial_coords.ix2),
        y2: Number(args.initial_coords.iy2),
      };
    }

    if (I.complete) {
      resize();
    } else {
      I.onload = resize;
    }

    draw();
    setFrameHeight(Math.ceil(C.height || I.height || 320) + 24);
  }

  window.addEventListener('message', onRender);
  setComponentReady();
})();
</script>
</body>
</html>
""",
            encoding="utf-8",
        )
    return components.declare_component("pdf_drag_selector", path=str(COMP_DIR))


# ── 座標変換 ──
def img_pixel_to_pdf(ix1, iy1, ix2, iy2, img_w, img_h, llx, lly, urx, ury, dpi=150):
    x1 = max(0.0, min(float(ix1), float(img_w)))
    x2 = max(0.0, min(float(ix2), float(img_w)))
    y1 = max(0.0, min(float(iy1), float(img_h)))
    y2 = max(0.0, min(float(iy2), float(img_h)))
    s = 72.0 / dpi
    return (llx + x1 * s, ury - y2 * s, llx + x2 * s, ury - y1 * s)


# ── ファイルアップロード or セッション復元 ──
uploaded = st.file_uploader("PDF をアップロード", type="pdf")
if uploaded is not None:
    buf = uploaded.getvalue()
    digest = hashlib.sha256(buf).hexdigest()
    is_new_file = digest != st.session_state.uploaded_hash

    st.session_state.uploaded_bytes = buf
    st.session_state.uploaded_name = uploaded.name

    if is_new_file:
        st.session_state.uploaded_hash = digest
        st.session_state.bbox_pt = None
        st.session_state.drag_raw = None
        st.session_state.drag_clear_nonce += 1

# session_state にキャッシュがあればそれを使う
if st.session_state.uploaded_bytes:
    buf = st.session_state.uploaded_bytes
    tmp = "/tmp/_pdf_upload.pdf"
    with open(tmp, "wb") as f:
        f.write(buf)
    
    try:
        doc = PdfDocument(tmp)
    except Exception as e:
        st.error(f"❌ PDF 読み込みエラー: {e}")
        st.stop()
    
    n = doc.page_count()
    st.info(f"ページ数: {n}（ファイル: {st.session_state.uploaded_name or 'unknown'}）")

    ref_page = st.number_input("参照ページ (0-based)", 0, n - 1, 0, step=1)
    llx, lly, urx, ury = doc.page_media_box(ref_page)
    pt_w = urx - llx
    pt_h = ury - lly
    st.caption(f"ページサイズ: {pt_w:.0f} × {pt_h:.0f} pt")

    DPI = 150
    try:
        server_info = get_image_server()
    except RuntimeError as exc:
        st.error(str(exc))
        st.stop()

    port = server_info["port"]
    images_dir = server_info["images_dir"]
    image_prefix = st.session_state.drag_session_id
    ref_img_filename = f"{image_prefix}_ref_page_{ref_page}.png"
    ref_img_path = images_dir / ref_img_filename
    
    # ── 画像生成 ──
    try:
        img_bytes = doc.render_page(ref_page, dpi=DPI, format="png")
        if not img_bytes or len(img_bytes) == 0:
            st.error("❌ PDF ページを画像に変換できませんでした（空の結果）")
            st.stop()
    except Exception as e:
        st.error(f"❌ PDF ページ描画エラー: {e}")
        st.stop()
    
    # ── 画像ファイル保存 ──
    try:
        ref_img_path.write_bytes(img_bytes)
        st.caption(f"✓ 画像保存: {ref_img_path} ({len(img_bytes)} bytes)")
    except Exception as e:
        st.error(f"❌ 画像ファイル書き込みエラー: {e}")
        st.stop()
    
    # クリーンアップ
    for stale_image in images_dir.glob(f"{image_prefix}_ref_page_*.png"):
        if stale_image.name != ref_img_filename:
            stale_image.unlink(missing_ok=True)

    from PIL import Image

    img = Image.open(io.BytesIO(img_bytes))
    iw, ih = img.size
    st.caption(f"✓ 画像寸法: {iw} × {ih} px")

    # 画像本体は base64 で渡さず、ローカルHTTPサーバーURLを渡す
    img_url = f"http://localhost:{port}/{ref_img_filename}"
    st.caption(f"画像URL: `{img_url}`")
    
    raw_coords = drag_component()(
        img_url=img_url,
        nw=iw,
        nh=ih,
        max_w=960,
        clear_nonce=st.session_state.drag_clear_nonce,
        initial_coords=st.session_state.drag_raw,
        key="drag_selector",
        default=None,
    )

    if isinstance(raw_coords, dict) and {"ix1", "iy1", "ix2", "iy2"}.issubset(raw_coords.keys()):
        c = {
            "ix1": float(raw_coords["ix1"]),
            "iy1": float(raw_coords["iy1"]),
            "ix2": float(raw_coords["ix2"]),
            "iy2": float(raw_coords["iy2"]),
        }
        st.session_state.drag_raw = c
        st.session_state.bbox_pt = img_pixel_to_pdf(
            c["ix1"], c["iy1"], c["ix2"], c["iy2"], iw, ih, llx, lly, urx, ury, DPI
        )

    if st.session_state.bbox_pt:
        x1, y1, x2, y2 = st.session_state.bbox_pt
        st.markdown(
            f"**範囲:** `({x1:.0f}, {y1:.0f}) → ({x2:.0f}, {y2:.0f})` pt"
            f" — 幅 {x2-x1:.0f}×高さ {y2-y1:.0f} pt"
        )
        if st.button("🔄 クリア"):
            st.session_state.bbox_pt = None
            st.session_state.drag_raw = None
            st.session_state.drag_clear_nonce += 1
            st.rerun()

    mode = st.radio("抽出モード", ["テキスト抽出", "マークダウン変換", "両方"], index=0)

    if st.button("🚀 処理開始", type="primary"):
        if not st.session_state.bbox_pt:
            st.warning("先に参照ページ上で範囲をドラッグ指定してください。")
        else:
            bbox = st.session_state.bbox_pt
            with st.spinner("PDF 解析中…"):
                text_result = ""
                md_result = ""

                if mode in ("テキスト抽出", "両方"):
                    lines = []
                    for i in range(n):
                        region = doc.within(i, bbox)
                        lines.append(f"--- Page {i + 1} ---\n{region.extract_text()}")
                    text_result = "\n".join(lines)

                if mode in ("マークダウン変換", "両方"):
                    lines = []
                    for i in range(n):
                        region = doc.within(i, bbox)
                        lines.append(f"--- Page {i + 1} ---\n{region.extract_text()}")
                    md_result = "\n".join(lines)

                st.success("処理完了！")

            col1, col2 = st.columns(2)
            if text_result:
                with col1:
                    st.subheader("📝 テキスト")
                    with st.expander("プレビュー", expanded=False):
                        st.text(text_result[:3000])
                    st.download_button(
                        label="📥 DL",
                        data=text_result,
                        file_name=f"text_{st.session_state.uploaded_name.replace('.pdf','.txt') if st.session_state.uploaded_name else 'output.txt'}",
                        mime="text/plain",
                    )
            if md_result:
                with col2:
                    st.subheader("📝 マークダウン")
                    with st.expander("プレビュー", expanded=False):
                        st.text(md_result[:3000])
                    st.download_button(
                        label="📥 DL",
                        data=md_result,
                        file_name=f"md_{st.session_state.uploaded_name.replace('.pdf','.md') if st.session_state.uploaded_name else 'output.md'}",
                        mime="text/markdown",
                    )
            if mode == "両方":
                st.download_button(
                    label="📥 両方DL",
                    data=(
                        "=" * 60
                        + "\nTEXT\n"
                        + "=" * 60
                        + "\n"
                        + text_result
                        + "\n\n"
                        + "=" * 60
                        + "\nMARKDOWN\n"
                        + "=" * 60
                        + "\n"
                        + md_result
                    ),
                    file_name=f"combined_{st.session_state.uploaded_name.replace('.pdf','.txt') if st.session_state.uploaded_name else 'output.txt'}",
                    mime="text/plain",
                )

st.caption(
    "① PDF アップロード → ② 参照ページ選択 → ③ 画像をドラッグして範囲指定 → "
    "④ 処理開始 → 全ページの指定範囲内テキストを抽出・ダウンロード"
)
