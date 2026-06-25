import fs from 'fs';
const body = JSON.parse(fs.readFileSync('cache/wecom-pilati-body.json', 'utf-8'));
const webhookUrl = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=6e09dd24-118b-4fea-bc6d-876e6947d975";

(async () => {
  const response = await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const result = await response.json();
  console.log("Status:", response.status);
  console.log("Response:", JSON.stringify(result, null, 2));
})();
