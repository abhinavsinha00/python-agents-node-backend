(function () {
  'use strict';

  let counterValue = 0;

  const displayEl = document.getElementById('counter-display');
  const incrementBtn = document.getElementById('increment-btn');
  const decrementBtn = document.getElementById('decrement-btn');

  function updateDisplay() {
    displayEl.textContent = String(counterValue);
  }

  function increment() {
    counterValue += 1;
    updateDisplay();
  }

  function decrement() {
    counterValue -= 1;
    updateDisplay();
  }

  incrementBtn.addEventListener('click', increment);
  decrementBtn.addEventListener('click', decrement);

  // Initialize display (script is deferred, so DOM is ready)
  updateDisplay();
})();