const messageInput = document.querySelector('#message');
const checkButton = document.querySelector('#check-button');
const errorMessage = document.querySelector('#error-message');
const emptyState = document.querySelector('#empty-state');
const prediction = document.querySelector('#prediction');

messageInput.addEventListener('input', () => {
  document.querySelector('#char-count').textContent = `${messageInput.value.length} / 5000`;
});

document.querySelectorAll('.example').forEach((button) => {
  button.addEventListener('click', () => {
    messageInput.value = button.dataset.message;
    messageInput.dispatchEvent(new Event('input'));
    messageInput.focus();
  });
});

checkButton.addEventListener('click', async () => {
  const text = messageInput.value.trim();
  errorMessage.hidden = true;
  if (!text) {
    errorMessage.textContent = 'Enter a message to check.';
    errorMessage.hidden = false;
    messageInput.focus();
    return;
  }

  checkButton.disabled = true;
  checkButton.querySelector('span:first-child').textContent = 'Checking…';
  try {
    const response = await fetch('/api/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'The message could not be checked.');
    showResult(result);
  } catch (error) {
    errorMessage.textContent = error.message || 'The service is unavailable. Try again.';
    errorMessage.hidden = false;
  } finally {
    checkButton.disabled = false;
    checkButton.querySelector('span:first-child').textContent = 'Check message';
  }
});

function showResult(result) {
  emptyState.hidden = true;
  prediction.hidden = false;
  const isSpam = result.label === 'spam';
  prediction.className = `prediction ${isSpam ? 'spam' : 'ham'}`;
  document.querySelector('#result-icon').textContent = isSpam ? '!' : '✓';
  document.querySelector('#result-label').textContent = isSpam ? 'Likely spam' : 'Likely normal';
  document.querySelector('#result-description').textContent = isSpam
    ? 'This message has patterns often found in spam texts. Be careful with links and requests for personal details.'
    : 'The model did not find strong spam signals in this message. Still check unexpected links carefully.';
  const score = Math.round(result.spam_probability * 100);
  document.querySelector('#spam-score').textContent = `${score}%`;
  document.querySelector('#score-meter').style.width = `${score}%`;
}

fetch('/health')
  .then((response) => response.json())
  .then((health) => {
    if (health.metrics) {
      const accuracy = Math.round(health.metrics.accuracy * 100);
      document.querySelector('#model-summary').textContent = `${health.metrics.test_samples} held-out messages · ${accuracy}% accuracy`;
    }
  })
  .catch(() => {
    document.querySelector('#model-summary').textContent = 'Model details unavailable';
  });
