# PDF テキスト・マークダウン抽出アプリ

pdf_oxide を使った Streamlit ウェブアプリ。PDF ファイルをアップロードすると、全ページからテキストまたはマークダウンを抽出してダウンロードできます。

## 機能

- PDF をアップロード → 全ページのテキスト抽出
- PDF をアップロード → 全ページのマークダウン変換（見出し自動検出）
- 両方同時に抽出することも可能
- 結果のプレビュー表示
- ワンクリックでダウンロード

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
2. 抽出モードを選択（テキスト / マークダウン / 両方）
3. 「処理開始」をクリック
4. 結果をプレビューしてダウンロード

## 構成

```
pdf-oxide-app/
├── app.py              # Streamlit アプリ本体
├── requirements.txt    # streamlit + pdf-oxide
├── Dockerfile          # python:3.11-slim ベース
├── .gitignore
└── README.md           # このファイル
```

## 技術詳細

内部で [pdf_oxide](https://pypi.org/project/pdf-oxide/) ライブラリを使用。
- `extract_text(i)` — ページ i のプレーンテキスト取得
- `to_markdown(i, detect_headings=True)` — ページ i のマークダウン変換（見出し・リンク自動変換）
