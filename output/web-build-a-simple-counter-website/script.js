const counterValueEl = document.getElementById("counter-value");
const incrementBtn = document.getElementById("increment-btn");
const decrementBtn = document.getElementById("decrement-btn");

let count = 0;

function renderCounter() {
  counterValueEl.textContent = String(count);
}

incrementBtn.addEventListener("click", function () {
  count += 1;
  renderCounter();
});

decrementBtn.addEventListener("click", function () {
  count -= 1;
  renderCounter();
});

renderCounter();