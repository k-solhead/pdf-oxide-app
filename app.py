"""
pdf-oxide-app — PDF 範囲指定テキスト抽出アプリ
参照ページを画像表示 → マウスドラッグで領域指定 → within() で絞って全ページ抽出
"""
import hashlib
import io
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


COMP_DIR = Path("/tmp/pdf_oxide_drag_component")
COMP_IMG_DIR = COMP_DIR / "images"


@st.cache_resource
def drag_component():
    COMP_DIR.mkdir(parents=True, exist_ok=True)
    COMP_IMG_DIR.mkdir(parents=True, exist_ok=True)
    index = COMP_DIR / "index.html"
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

    if (args.img_path && args.img_path !== currentImage) {
      currentImage = args.img_path;
      I.src = new URL(args.img_path, window.location.href).toString();
      I.onerror = function() {
        console.error('Failed to load image');
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


def save_component_image(img_bytes: bytes, image_key: str) -> str:
    COMP_IMG_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{image_key}.png"
    image_path = COMP_IMG_DIR / filename
    image_path.write_bytes(img_bytes)
    return f"images/{filename}"


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

    # ── 画像生成 ──
    try:
        img_bytes = doc.render_page(ref_page, dpi=DPI, format="png")
        if not img_bytes or len(img_bytes) == 0:
            st.error("❌ PDF ページを画像に変換できませんでした（空の結果）")
            st.stop()
    except Exception as e:
        st.error(f"❌ PDF ページ描画エラー: {e}")
        st.stop()

    from PIL import Image

    with Image.open(io.BytesIO(img_bytes)) as img:
        iw, ih = img.size
    st.caption(f"✓ 画像寸法: {iw} × {ih} px")

    image_hash = hashlib.sha256(img_bytes).hexdigest()[:16]
    image_key = f"{st.session_state.uploaded_hash}_page{ref_page}_dpi{DPI}_{image_hash}"
    img_path = save_component_image(img_bytes, image_key)
    st.caption(f"✓ 選択中の参照ページ画像をコンポーネント用ファイルとして保存しました ({len(img_bytes)} bytes)")
    
    raw_coords = drag_component()(
        img_path=img_path,
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
