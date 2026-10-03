# GAS連携

Google Apps ScriptからGitHub Actionsを起動し、1日3回の通常投稿、3日ごとの無料鑑定募集、15分ごとのコメント返信を実行します。

コメントへの自動返信は、GASの `runThreadsAutoReply` が15分ごとにGitHub Actionsの `.github/workflows/reply.yml` を起動します。返信対象は直近48時間の短い通常コメントのみです。無料鑑定の募集投稿には、アカウントのフォローとプロフィールサイトからの追加をお願いし、数回やり取りした後に鑑定書を送る流れを丁寧に伝える複数の定型文を使い分けます。質問、URL、個人情報、医療・法律・金銭・深刻な相談、攻撃的な内容は自動返信せず、人による確認対象としてログに残します。同じコメントに自分の返信がある場合は再返信しません。

自動返信には、Threadsアクセストークンへ次の権限が必要です。

- `threads_read_replies`
- `threads_manage_replies`
- `threads_basic`
- `threads_content_publish`

## 投稿構成

- 朝: `postMorningLoveMessage` -> 恋愛お姉さんの朝ひとこと
- 昼: `postNoonLoveMessage` -> 恋愛お姉さんの昼ひとこと
- 夕方: `postEveningLoveRanking` -> 明日の恋愛運TOP5ランキング
- 3日ごと: `postFreeReadingOffer` -> 当日の日付入り無料タロット鑑定募集
  - 投稿時刻は朝8時・昼13時・夜20時から毎回ランダムに選択
  - 応募方法はコメント欄の「鑑定希望」

## 初期設定

1. Google Apps Scriptに `Code.gs` の内容を貼り付ける
2. GASの「プロジェクトの設定」→「スクリプト プロパティ」に追加
   - `GITHUB_TOKEN`: GitHub fine-grained token
3. GitHub tokenには対象リポジトリへの `Actions: Read and write` 権限を付ける
4. GAS上で `setupDailyTriggers` を1回実行する
5. GAS上で `checkDailyTriggers` を実行し、実行ログに5つのトリガーが出ることを確認する

## 時間実行の確認

`setupDailyTriggers` を1回実行すると、Asia/Tokyo基準で以下の時間トリガーが作成されます。

- 8時台: `postMorningLoveMessage`
- 12時台: `postNoonLoveMessage`
- 18時台: `postEveningLoveRanking`
- 15分ごと: `runThreadsAutoReply`
- 3日ごと: `postFreeReadingOffer`（朝8時・昼13時・夜20時からランダム）

Apps Scriptの時間主導型トリガーは、指定分ちょうどではなく近い時間に実行されます。

GAS上で `checkDailyTriggers` を実行し、実行ログに以下の5つが出れば設定済みです。

- `postMorningLoveMessage`
- `postNoonLoveMessage`
- `postEveningLoveRanking`
- `postFreeReadingOffer`
- `runThreadsAutoReply`

## 手動テスト

GAS上で以下の関数を1つずつ実行します。

- `postMorningLoveMessage`
- `postNoonLoveMessage`
- `postEveningLoveRanking`
- `postFreeReadingOffer`
- `testThreadsAutoReplyDryRun`（返信せず、対象確認だけを行う接続テスト）

実返信の手動確認が必要な場合のみ `runThreadsAutoReply` を実行します。

GitHub Actionsの実行履歴に起動ログが出れば成功です。

## claspで同期する場合

初回だけGoogleログインとScript IDの設定が必要です。

```bash
npm install -g @google/clasp
clasp login
cp .clasp.json.example .clasp.json
```

`.clasp.json` の `YOUR_GAS_SCRIPT_ID` をGASのScript IDに置き換えます。

```json
{
  "scriptId": "GASのScript ID",
  "rootDir": "gas"
}
```

GASへ反映:

```bash
clasp push
```

GASからローカルへ取り込み:

```bash
clasp pull
```
