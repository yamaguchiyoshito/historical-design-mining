# GitHub登録とPages公開

[連載目次へ](../README.md)

## 方式

`main` ブランチへのpushで `.github/workflows/pages.yml` が検査・ビルド・配置を行う。GitHub Pagesの Source は **GitHub Actions** にする。配置されるのは `_site/` の読者用出力であり、Markdown原本、スクリプト、テストはサイトに含めない。

準備するもの：Git、GitHub CLI（`gh`）、Python 3.12以降、Pandoc 3.x。CIでは Pandoc 3.7.0.2 に固定している。トークンを原稿・設定・コマンド引数へ貼り付けない。

```sh
gh auth status
```

## 公開前の確認

```sh
python3 scripts/draw_figures.py
python3 scripts/validate.py
python3 -m unittest discover -s tests
python3 scripts/build.py
python3 scripts/check_html.py
```

あわせて `editorial/verification-log.md` の未解決事項を確認する。AGENTS.md の完成判定を満たしていない点は、公開前に著者が判断する。

## 新規リポジトリを作成する

```sh
gh repo create yamaguchiyoshito/historical-design-mining --public --source=. --remote=origin
git push -u origin main
```

既存コンテンツのあるリポジトリへ強制pushしない。公開範囲の変更は手作業で判断する。GitHub Pagesは公開リポジトリでは無料で使える。非公開リポジトリでの利用は契約に依存する。

## GitHub Pagesを有効にする

Settings → Pages → Build and deployment で Source を **GitHub Actions** にする。CLIでは次のとおり。

```sh
gh api -X POST repos/yamaguchiyoshito/historical-design-mining/pages -f build_type=workflow
```

以後、`main` へのpushごとに `Publish to GitHub Pages` が実行される。初回は Actions タブから手動実行してもよい。公開URLは成功したデプロイの `github-pages` 環境から取得し、推測したURLを案内しない。

## CI設定の保守

`validate.yml` は `contents: read` のみとし、`pages.yml` の公開ジョブにだけ `pages: write` と `id-token: write` を与える。Actionsの主要バージョンは作成時点の公開情報に基づくため、定期的に確認する。
