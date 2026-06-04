/**
 * Google Apps ScriptからGitHub Actionsのpost.ymlを起動するコード。
 *
 * 事前にGASの「プロジェクトの設定」→「スクリプト プロパティ」で以下を設定してください。
 * GITHUB_TOKEN: GitHub fine-grained token（Actions: Read and write）
 */

const GITHUB_OWNER = 'tora1128';
const GITHUB_REPO = 'diet-threads-bot';
const GITHUB_WORKFLOW = 'post.yml';
const GITHUB_REF = 'main';

function postMorningLoveMessage() {
  dispatchGitHubAction_({
    post_type: 'morning_message',
    category: '恋愛運',
    date_offset: '',
  });
}

function postNoonLoveMessage() {
  dispatchGitHubAction_({
    post_type: 'noon_message',
    category: '恋愛運',
    date_offset: '',
  });
}

function postEveningLoveRanking() {
  dispatchGitHubAction_({
    post_type: 'ranking',
    category: '恋愛運',
    date_offset: '1',
  });
}

function setupDailyTriggers() {
  deleteDietBotTriggers_();

  ScriptApp.newTrigger('postMorningLoveMessage')
    .timeBased()
    .everyDays(1)
    .atHour(8)
    .nearMinute(0)
    .create();

  ScriptApp.newTrigger('postNoonLoveMessage')
    .timeBased()
    .everyDays(1)
    .atHour(12)
    .nearMinute(0)
    .create();

  ScriptApp.newTrigger('postEveningLoveRanking')
    .timeBased()
    .everyDays(1)
    .atHour(18)
    .nearMinute(0)
    .create();
}

function deleteDietBotTriggers_() {
  const targetFunctions = [
    'postMorningLoveMessage',
    'postNoonLoveMessage',
    'postEveningLoveRanking',
  ];

  ScriptApp.getProjectTriggers().forEach((trigger) => {
    if (targetFunctions.includes(trigger.getHandlerFunction())) {
      ScriptApp.deleteTrigger(trigger);
    }
  });
}

function dispatchGitHubAction_(inputs) {
  const token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) {
    throw new Error('GITHUB_TOKEN がスクリプト プロパティに設定されていません');
  }

  const url = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${GITHUB_WORKFLOW}/dispatches`;
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
  Logger.log(`GitHub Actions dispatch: ${status} ${body}`);

  if (status < 200 || status >= 300) {
    throw new Error(`GitHub Actions起動失敗: ${status} ${body}`);
  }
}
