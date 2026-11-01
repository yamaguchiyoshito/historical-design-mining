# 古い器に新しい水を入れる

**過去の知を発掘し、AIエージェントによって再実装する**

過去の論文・文章に記述された技術的構想を、単なる歴史資料ではなく、現代の技術で実装可能な設計資産として読み直す全4回の連載。

## 目次

1. [第1回：過去の文章は、未来の設計書である](articles/01-past-texts-as-future-designs.md)
2. [第2回：歴史の中に埋もれた設計を発掘する](articles/02-excavating-forgotten-designs.md)
3. [第3回：文献を読むAIから、設計を発掘するAIへ](articles/03-from-reading-to-mining-agent.md)
4. [第4回：古い器に、新しい水を入れる](articles/04-reimplementing-old-ideas.md)

## AIによる完成稿の編集

AIコーディングエージェント（Codex、Claude Codeなど）にリポジトリを開かせ、[AGENTS.md](AGENTS.md) の指示に従って4本を校正・検証する。原稿の論旨を維持し、史実の出典確認、仮説と実績の区別、記事間の整合性を点検する。実行時の指示例と完成判定は `AGENTS.md` に収録。

## 構成

```text
historical-design-mining/
├── README.md
├── AGENTS.md              # AI編集エージェント指示書
├── articles/
│   ├── 01-past-texts-as-future-designs.md
│   ├── 02-excavating-forgotten-designs.md
│   ├── 03-from-reading-to-mining-agent.md
│   └── 04-reimplementing-old-ideas.md
└── .gitignore
```

## 管理方針

- 記事は1回につき1ファイル、ファイル名の数字順に掲載する。
- 見出しはMarkdownの `#`（連載名）と `##`（回とタイトル）、`###`（節）を用いる。
- 出典は各記事の末尾に記録し、未確認の仮説と確認済みの先行研究を区別する。
- 原稿の修正はGitの履歴に残し、公開前の校正はPull Requestでレビューする。

## GitHubへの登録

```bash
git init
git add .
git commit -m "docs: add four-part essay series"
git branch -M main
git remote add origin https://github.com/USERNAME/historical-design-mining.git
git push -u origin main
```

上記の `USERNAME` は自分のGitHubユーザー名に置き換える。GitHub側で空のリポジトリを事前に作成しておく。

## ライセンス

原稿の著作権・利用条件はリポジトリ所有者が設定する。明示的なライセンスは未設定。
