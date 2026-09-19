"""
pdf-oxide-app — PDF 範囲指定テキスト抽出アプリ
参照ページを画像表示 → マウスドラッグで領域指定 → within() で絞って全ページ抽出
"""
import io
import json
import base64
import streamlit as st
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

# ── HTML: 画像上ドラッグ → 矩形座標 (画像ピクセル) ──
def drag_html(img_b64: str, nw: int, nh: int, max_w: int = 960) -> str:
    return f"""<!DOCTYPE html>
<html><head>
</head><body style="margin:0;padding:0;background:#1e1e1e;text-align:center;">
<div style="position:relative;display:inline-block;max-width:{max_w}px;width:100%;">
  <img id="P" src="data:image/png;base64,{img_b64}"
       style="display:block;width:100%;height:auto;cursor:crosshair;" crossorigin="anonymous" />
  <canvas id="C" style="position:absolute;left:0;top:0;width:100%;height:100%;cursor:crosshair;"></canvas>
</div>
<script>
(function(){{
const I=document.getElementById('P'),C=document.getElementById('C'),ctx=C.getContext('2d');
const NW={nw},NH={nh}; let drag=0, rx=0,ry=0,rx2=0,ry2=0;
function sz(){{ const r=I.getBoundingClientRect(); C.width=r.width; C.height=r.height; }}
I.addEventListener('load',sz); window.addEventListener('resize',sz);
function ic(e){{ const r=I.getBoundingClientRect();
  return {{ix:(e.clientX-r.left)/r.width*NW, iy:(e.clientY-r.top)/r.height*NH}}; }}
function draw(){{
  ctx.clearRect(0,0,C.width,C.height);
  if(!drag && rx===0) return;
  const r=I.getBoundingClientRect(), s=C.width/r.width;
  const x1=rx*s/NW*r.width, y1=ry*s/NH*r.height, x2=rx2*s/NW*r.width, y2=ry2*s/NH*r.height;
  ctx.strokeStyle='#00ff88'; ctx.lineWidth=2; ctx.setLineDash([6,4]);
  ctx.strokeRect(x1,y1,x2-x1,y2-y1); ctx.setLineDash([]);
  ctx.fillStyle='rgba(0,255,136,0.15)'; ctx.fillRect(x1,y1,x2-x1,y2-y1);
}}
C.addEventListener('mousedown',e=>{{drag=1; let p=ic(e); rx=p.ix; ry=p.iy; rx2=p.ix; ry2=p.iy; draw();}});
C.addEventListener('mousemove',e=>{{if(!drag)return; let p=ic(e); rx2=p.ix; ry2=p.iy; draw();}});
window.addEventListener('mouseup',e=>{{
  if(!drag)return; drag=0;
  const x1=Math.min(rx,rx2),y1=Math.min(ry,ry2),x2=Math.max(rx,rx2),y2=Math.max(ry,ry2);
  if(x2-x1<10||y2-y1<10){{return;}}
  const p = new URLSearchParams(window.parent.location.search);
  p.set('coords', JSON.stringify({{ix1:x1,iy1:y1,ix2:x2,iy2:y2}}));
  window.parent.location.search = p.toString();
}});
sz();
}})();
</script></body></html>"""

# ── 座標変換 ──
def img_pixel_to_pdf(ix1, iy1, ix2, iy2, img_w, img_h, llx, lly, urx, ury, dpi=150):
    s = 72.0 / dpi
    return (llx + ix1 * s, ury - iy2 * s, llx + ix2 * s, ury - iy1 * s)

# ── query_params から座標を処理 ──
def process_coords(iw, ih, llx, lly, urx, ury):
    raw = st.query_params.get("coords")
    if raw:
        if isinstance(raw, list):
            raw = raw[0]
        try:
            c = json.loads(raw)
            bbox = img_pixel_to_pdf(c["ix1"], c["iy1"], c["ix2"], c["iy2"],
                                     iw, ih, llx, lly, urx, ury, DPI)
            st.session_state.bbox_pt = bbox
            st.session_state.drag_raw = c
            st.query_params.clear()
        except Exception as e:
            st.warning(f"座標パースエラー: {e}")
            st.query_params.clear()

# ── ファイルアップロード or セッション復元 ──
uploaded = st.file_uploader("PDF をアップロード", type="pdf")
if uploaded:
    buf = uploaded.read()
    st.session_state.uploaded_bytes = buf
    st.session_state.uploaded_name = uploaded.name
    # session_state は通常の rerun でもフルリロードでも保持されるので rerun 不要

# session_state にキャッシュがあればそれを使う
if st.session_state.uploaded_bytes:
    buf = st.session_state.uploaded_bytes
    tmp = "/tmp/_pdf_upload.pdf"
    with open(tmp, "wb") as f:
        f.write(buf)
    doc = PdfDocument(tmp)
    n = doc.page_count()
    st.info(f"ページ数: {n}（ファイル: {st.session_state.uploaded_name or 'unknown'}）")

    ref_page = st.number_input("参照ページ (0-based)", 0, n - 1, 0, step=1)
    llx, lly, urx, ury = doc.page_media_box(ref_page)
    pt_w = urx - llx
    pt_h = ury - lly
    st.caption(f"ページサイズ: {pt_w:.0f} × {pt_h:.0f} pt")

    DPI = 150
    img_bytes = doc.render_page(ref_page, dpi=DPI, format="png")
    b64 = base64.b64encode(img_bytes).decode()
    from PIL import Image
    img = Image.open(io.BytesIO(img_bytes))
    iw, ih = img.size

    # query_params 経由の座標を処理（リロード後も session_state が生きてる）
    process_coords(iw, ih, llx, lly, urx, ury)

    # html() で iframe 描画
    st.components.v1.html(drag_html(b64, iw, ih, 960),
                          height=int(960 * ih / iw) + 40,
                          scrolling=False)

    if st.session_state.bbox_pt:
        x1, y1, x2, y2 = st.session_state.bbox_pt
        st.markdown(f"**範囲:** `({x1:.0f}, {y1:.0f}) → ({x2:.0f}, {y2:.0f})` pt"
                    f" — 幅 {x2-x1:.0f}×高さ {y2-y1:.0f} pt")
        if st.button("🔄 クリア"):
            st.session_state.bbox_pt = None
            st.session_state.drag_raw = None
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
                        label="📥 DL", data=text_result,
                        file_name=f"text_{st.session_state.uploaded_name.replace('.pdf','.txt') if st.session_state.uploaded_name else 'output.txt'}",
                        mime="text/plain",
                    )
            if md_result:
                with col2:
                    st.subheader("📝 マークダウン")
                    with st.expander("プレビュー", expanded=False):
                        st.text(md_result[:3000])
                    st.download_button(
                        label="📥 DL", data=md_result,
                        file_name=f"md_{st.session_state.uploaded_name.replace('.pdf','.md') if st.session_state.uploaded_name else 'output.md'}",
                        mime="text/markdown",
                    )
            if mode == "両方":
                st.download_button(
                    label="📥 両方DL",
                    data=("="*60+"\nTEXT\n"+"="*60+"\n"+text_result+
                          "\n\n"+"="*60+"\nMARKDOWN\n"+"="*60+"\n"+md_result),
                    file_name=f"combined_{st.session_state.uploaded_name.replace('.pdf','.txt') if st.session_state.uploaded_name else 'output.txt'}",
                    mime="text/plain",
                )

st.caption(
    "① PDF アップロード → ② 参照ページ選択 → ③ 画像をドラッグして範囲指定 → "
    "④ 処理開始 → 全ページの指定範囲内テキストを抽出・ダウンロード"
)
