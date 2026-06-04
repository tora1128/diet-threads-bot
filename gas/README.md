# GAS連携

Google Apps ScriptからGitHub Actionsの `post.yml` を起動して、1日3回投稿します。

## 投稿構成

- 朝: `postMorningLoveMessage` -> 恋愛お姉さんの朝ひとこと
- 昼: `postNoonLoveMessage` -> 恋愛お姉さんの昼ひとこと
- 夕方: `postEveningLoveRanking` -> 明日の恋愛運TOP5ランキング

## 初期設定

1. Google Apps Scriptに `Code.gs` の内容を貼り付ける
2. GASの「プロジェクトの設定」→「スクリプト プロパティ」に追加
   - `GITHUB_TOKEN`: GitHub fine-grained token
3. GitHub tokenには対象リポジトリへの `Actions: Read and write` 権限を付ける
4. GAS上で `setupDailyTriggers` を1回実行する

## 手動テスト

GAS上で以下の関数を1つずつ実行します。

- `postMorningLoveMessage`
- `postNoonLoveMessage`
- `postEveningLoveRanking`

GitHub Actionsの実行履歴に起動ログが出れば成功です。
