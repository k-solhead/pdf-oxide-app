import streamlit as st
import io
from pdf_oxide import PdfDocument

st.set_page_config(page_title="PDF テキスト/マークダウン抽出", layout="wide")
st.title("📄 PDF テキスト・マークダウン抽出")
st.markdown(
    "pdf_oxide を使って PDF の全ページからテキストまたはマークダウンを抽出します。"
)

uploaded = st.file_uploader("PDF ファイルをアップロード", type="pdf")

mode = st.radio(
    "抽出モード",
    ["テキスト抽出", "マークダウン変換", "両方（テキスト＋マークダウン）"],
    index=0,
)

if uploaded and st.button("🚀 処理開始", type="primary"):
    with st.spinner("PDF を読み込み中..."):
        buf = uploaded.read()
        # bytes をファイルのように扱うため一時ファイル経由
        tmp_path = "/tmp/_pdf_upload.pdf"
        with open(tmp_path, "wb") as f:
            f.write(buf)

        doc = PdfDocument(tmp_path)
        n = doc.page_count()
        st.info(f"ページ数: {n}")

        # モード別に処理
        text_result = ""
        md_result = ""

        if mode in ("テキスト抽出", "両方（テキスト＋マークダウン）"):
            with st.spinner("テキスト抽出中..."):
                lines = []
                for i in range(n):
                    t = doc.extract_text(i)
                    lines.append(f"--- Page {i + 1} ---\n{t}")
                text_result = "\n".join(lines)

        if mode in ("マークダウン変換", "両方（テキスト＋マークダウン）"):
            with st.spinner("マークダウン変換中..."):
                lines = []
                for i in range(n):
                    md = doc.to_markdown(i, detect_headings=True)
                    lines.append(f"--- Page {i + 1} ---\n{md}")
                md_result = "\n".join(lines)

        st.success("処理完了！")

        # 結果表示
        col1, col2 = st.columns(2)

        if text_result:
            with col1:
                st.subheader("📝 テキスト")
                with st.expander("プレビュー", expanded=False):
                    st.text(text_result[:2000])
                st.download_button(
                    label="📥 テキストをダウンロード",
                    data=text_result,
                    file_name=f"text_{uploaded.name.replace('.pdf', '.txt')}",
                    mime="text/plain",
                )

        if md_result:
            with col2:
                st.subheader("📝 マークダウン")
                with st.expander("プレビュー", expanded=False):
                    st.text(md_result[:2000])
                st.download_button(
                    label="📥 マークダウンをダウンロード",
                    data=md_result,
                    file_name=f"markdown_{uploaded.name.replace('.pdf', '.md')}",
                    mime="text/markdown",
                )

        # 両方の場合は統合ダウンロードも提供
        if mode == "両方（テキスト＋マークダウン）":
            combined = (
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
            )
            st.download_button(
                label="📥 両方まとめてダウンロード",
                data=combined,
                file_name=f"combined_{uploaded.name.replace('.pdf', '.txt')}",
                mime="text/plain",
            )

st.caption(
    "Powered by pdf_oxide — テキスト抽出とマークダウン変換を選択して全ページ処理します。"
)
