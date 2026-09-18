# PDF 範囲指定テキスト抽出アプリ (pdf-oxide-app)

pdf_oxide を使った Streamlit ウェブアプリ。PDF の参照ページを画像表示し、マウスドラッグで **抽出したい領域**（ヘッダー・フッター・装飾を除いた本文部分）を指定。`within()` で範囲を絞って全ページからテキストを取得・ダウンロードできます。

## 機能

- PDF をアップロード → 参照ページを画像表示
- **マウスドラッグ** で矩形領域を指定（抽出したい範囲を選択）
- `within()` で PDF 座標に変換し、その範囲内のテキストのみを全ページから抽出
- テキスト抽出 / マークダウン変換 / 両方 のモード切替
- 結果のプレビュー表示 + ワンクリックダウンロード

## クイックスタート

### ローカル

```bash
pip install -r requirements.txt
streamlit run app.py
```

ブラウザで `http://localhost:8501` を開く。

### Docker

```bash
docker build -t pdf-oxide-app .
docker run -p 8501:8501 pdf-oxide-app
```

## 使い方

1. PDF ファイルをアップロード
2. 参照ページ番号を選択（範囲指定の目安にするページ）
3. 表示されたページ画像を **マウスドラッグ** で矩形選択
   - ヘッダー・フッター・装飾などを除外したい場合、本文部分だけを囲む
4. 抽出モードを選択（テキスト / マークダウン / 両方）
5. 「処理開始」をクリック → 全ページの指定範囲内テキストが抽出される
6. 結果をプレビューしてダウンロード

## 技術詳細

- `pdf_oxide.PdfDocument.within(page, bbox)` — 指定ページの抽出範囲を PDF 点座標で設定
- `PdfPageRegion.extract_text()` — その範囲内のテキストのみを返す
- マウスドラッグ座標 → 画像ピクセル → PDF 点座標 の変換は `img_pixel_to_pdf()` で行う
- レンダリング DPI=150、画像ピクセルと PDF 点の比率は `72/DPI`

## 構成

```
pdf-oxide-app/
├── app.py              # Streamlit アプリ本体
├── requirements.txt    # streamlit + pdf-oxide
├── Dockerfile          # python:3.11-slim ベース
├── .gitignore
└── README.md           # このファイル
```

## 制限

- PdfPageRegion には `to_markdown()` がないため、マークダウンモードでもプレーンテキストとして出力されます
- 範囲指定は全ページに同じ矩形領域が適用されます（ページごとに個別設定は不可）
