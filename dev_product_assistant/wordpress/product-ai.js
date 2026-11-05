(function () {
  'use strict';
  const cfg = window.bzbProductAI;
  const button = document.querySelector('[data-bzb-product-ai-open]');
  const layer = document.querySelector('.bzb-product-ai-layer');
  const panel = document.querySelector('.bzb-product-ai-panel');
  const log = document.querySelector('.bzb-product-ai-messages');
  const form = document.querySelector('.bzb-product-ai-form');
  const input = document.querySelector('#bzb-product-ai-input');
  if (!cfg || !button || !layer || !panel || !log || !form || !input) return;

  const title = document.querySelector('.product_title');
  if (title) title.insertAdjacentElement('afterend', button);
  else button.hidden = true;
  let history = [];
  let busy = false;
  let lastFocus = null;

  function addMessage(role, text, sources) {
    const article = document.createElement('article');
    article.className = 'bzb-product-ai-message bzb-product-ai-message--' + role;
    const body = document.createElement('div');
    body.className = 'bzb-product-ai-message__text';
    body.textContent = text;
    article.append(body);
    if (Array.isArray(sources) && sources.length) {
      const links = document.createElement('div');
      links.className = 'bzb-product-ai-sources';
      sources.forEach(function (source) {
        if (!source.url || !/^https:\/\/((www\.)?bzbgear\.com|dev\.bzbgear\.com)\//.test(source.url)) return;
        const a = document.createElement('a');
        a.href = source.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
        a.textContent = '[' + source.number + '] ' + source.title;
        links.append(a);
      });
      article.append(links);
    }
    log.append(article);
    log.scrollTop = log.scrollHeight;
    return article;
  }

  function open() {
    lastFocus = document.activeElement;
    layer.hidden = false;
    document.documentElement.classList.add('bzb-product-ai-open');
    if (!log.children.length) addMessage('assistant', 'Ask me about this product’s specs, connections, setup, or documentation.');
    input.focus();
  }
  function close() {
    layer.hidden = true;
    document.documentElement.classList.remove('bzb-product-ai-open');
    (lastFocus || button).focus();
  }
  button.addEventListener('click', open);
  layer.querySelectorAll('[data-bzb-product-ai-close]').forEach(function (node) { node.addEventListener('click', close); });
  document.addEventListener('keydown', function (event) {
    if (layer.hidden) return;
    if (event.key === 'Escape') close();
    if (event.key !== 'Tab') return;
    const focusable = Array.from(panel.querySelectorAll('button, input, a[href]')).filter(function (node) { return !node.disabled; });
    if (!focusable.length) return;
    if (event.shiftKey && document.activeElement === focusable[0]) { event.preventDefault(); focusable[focusable.length - 1].focus(); }
    if (!event.shiftKey && document.activeElement === focusable[focusable.length - 1]) { event.preventDefault(); focusable[0].focus(); }
  });

  async function ask(question) {
    if (busy || !question.trim()) return;
    busy = true;
    input.value = '';
    form.querySelector('button').disabled = true;
    addMessage('user', question);
    const pending = addMessage('assistant', 'Checking product materials…');
    try {
      const data = new URLSearchParams({ action: 'bzb_product_ai_ask', nonce: cfg.nonce,
        product_id: String(cfg.productId), question: question, history: JSON.stringify(history.slice(-8)) });
      const response = await fetch(cfg.api, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
        body: data.toString()
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.message || 'Please try again.');
      pending.remove();
      addMessage('assistant', result.answer, result.sources);
      history.push({ role: 'user', content: question }, { role: 'assistant', content: result.answer });
      history = history.slice(-12);
    } catch (error) {
      pending.remove();
      addMessage('error', error.message || 'Please try again.');
    } finally {
      busy = false;
      form.querySelector('button').disabled = false;
      input.focus();
    }
  }
  form.addEventListener('submit', function (event) { event.preventDefault(); ask(input.value); });
  layer.querySelectorAll('[data-bzb-question]').forEach(function (node) {
    node.addEventListener('click', function () { ask(node.dataset.bzbQuestion); });
  });
})();
