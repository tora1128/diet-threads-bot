/**
 * Google Apps ScriptからGitHub Actionsの投稿・返信ワークフローを起動するコード。
 *
 * 事前にGASの「プロジェクトの設定」→「スクリプト プロパティ」で以下を設定してください。
 * GITHUB_TOKEN: GitHub fine-grained token（Actions: Read and write）
 */

const GITHUB_OWNER = 'tora1128';
const GITHUB_REPO = 'diet-threads-bot';
const GITHUB_POST_WORKFLOW = 'post.yml';
const GITHUB_REPLY_WORKFLOW = 'reply.yml';
const GITHUB_REF = 'main';
const TRIGGER_TIMEZONE = 'Asia/Tokyo';
const FREE_READING_HOURS = [8, 13, 20];

function postMorningLoveMessage() {
  dispatchGitHubAction_(GITHUB_POST_WORKFLOW, {
    post_type: 'morning_message',
    category: '恋愛運',
    date_offset: '',
  });
}

function postNoonLoveMessage() {
  dispatchGitHubAction_(GITHUB_POST_WORKFLOW, {
    post_type: 'noon_message',
    category: '恋愛運',
    date_offset: '',
  });
}

function postEveningLoveRanking() {
  dispatchGitHubAction_(GITHUB_POST_WORKFLOW, {
    post_type: 'ranking',
    category: '恋愛運',
    date_offset: '1',
  });
}

/**
 * 無料鑑定の募集投稿を実行し、次回（3日後）の時刻をランダムに予約する。
 */
function postFreeReadingOffer() {
  dispatchGitHubAction_(GITHUB_POST_WORKFLOW, {
    post_type: 'free_reading',
    category: '恋愛運',
    date_offset: '0',
  });

  scheduleNextFreeReadingPost_(new Date(), 3);
}

function runThreadsAutoReply() {
  dispatchGitHubAction_(GITHUB_REPLY_WORKFLOW, {
    dry_run: false,
  });
}

function testThreadsAutoReplyDryRun() {
  dispatchGitHubAction_(GITHUB_REPLY_WORKFLOW, {
    dry_run: true,
  });
}

function setupDailyTriggers() {
  deleteDietBotTriggers_();

  ScriptApp.newTrigger('postMorningLoveMessage')
    .timeBased()
    .everyDays(1)
    .atHour(8)
    .nearMinute(0)
    .inTimezone(TRIGGER_TIMEZONE)
    .create();

  ScriptApp.newTrigger('postNoonLoveMessage')
    .timeBased()
    .everyDays(1)
    .atHour(12)
    .nearMinute(0)
    .inTimezone(TRIGGER_TIMEZONE)
    .create();

  ScriptApp.newTrigger('postEveningLoveRanking')
    .timeBased()
    .everyDays(1)
    .atHour(18)
    .nearMinute(0)
    .inTimezone(TRIGGER_TIMEZONE)
    .create();

  ScriptApp.newTrigger('runThreadsAutoReply')
    .timeBased()
    .everyMinutes(15)
    .create();

  // 初回は当日の残りの候補時刻から選び、以後は投稿のたびに3日後を予約する。
  scheduleFirstFreeReadingPost_();

  checkDailyTriggers();
}

function scheduleFirstFreeReadingPost_() {
  const now = new Date();
  const remainingHours = FREE_READING_HOURS.filter((hour) => hour > now.getHours());

  if (remainingHours.length > 0) {
    createFreeReadingTrigger_(now, randomChoice_(remainingHours));
    return;
  }

  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  createFreeReadingTrigger_(tomorrow, randomChoice_(FREE_READING_HOURS));
}

function scheduleNextFreeReadingPost_(lastPostedAt, daysLater) {
  const nextDate = new Date(lastPostedAt);
  nextDate.setDate(nextDate.getDate() + daysLater);
  createFreeReadingTrigger_(nextDate, randomChoice_(FREE_READING_HOURS));
}

function createFreeReadingTrigger_(date, hour) {
  const scheduledAt = new Date(date);
  scheduledAt.setHours(hour, 0, 0, 0);

  ScriptApp.newTrigger('postFreeReadingOffer')
    .timeBased()
    .at(scheduledAt)
    .create();

  Logger.log(
    `次回の無料鑑定募集: ${Utilities.formatDate(
      scheduledAt,
      TRIGGER_TIMEZONE,
      'yyyy-MM-dd HH:mm'
    )}`
  );
}

function randomChoice_(values) {
  return values[Math.floor(Math.random() * values.length)];
}

function checkDailyTriggers() {
  const triggers = ScriptApp.getProjectTriggers();
  Logger.log(`trigger count: ${triggers.length}`);

  triggers.forEach((trigger) => {
    Logger.log(
      [
        trigger.getHandlerFunction(),
        trigger.getEventType(),
        trigger.getTriggerSource(),
      ].join(' / ')
    );
  });
}

function deleteDietBotTriggers_() {
  const targetFunctions = [
    'postMorningLoveMessage',
    'postNoonLoveMessage',
    'postEveningLoveRanking',
    'postFreeReadingOffer',
    'runThreadsAutoReply',
  ];

  ScriptApp.getProjectTriggers().forEach((trigger) => {
    if (targetFunctions.includes(trigger.getHandlerFunction())) {
      ScriptApp.deleteTrigger(trigger);
    }
  });
}

function dispatchGitHubAction_(workflow, inputs) {
  const token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) {
    throw new Error('GITHUB_TOKEN がスクリプト プロパティに設定されていません');
  }

  const url = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${workflow}/dispatches`;
  const payload = {
    ref: GITHUB_REF,
    inputs,
  };

  const response = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
  });

  const status = response.getResponseCode();
  const body = response.getContentText();
  Logger.log(`GitHub Actions dispatch (${workflow}): ${status} ${body}`);

  if (status < 200 || status >= 300) {
    throw new Error(`GitHub Actions起動失敗: ${status} ${body}`);
  }
}
