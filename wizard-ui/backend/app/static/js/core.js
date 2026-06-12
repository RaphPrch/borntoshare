// wizard/js/core.js
import { stepStatus } from "./state.js";
import { logInfo } from "./logger.js";

const STEPS = [1, 2, 3, 4, 5, 6];
let currentStep = 1;

export function getCurrentStep() {
  return currentStep;
}

export function showStep(step) {
  const s = Number(step);
  if (!STEPS.includes(s)) {
    console.warn("[WIZARD] Invalid step:", step);
    return;
  }

  currentStep = s;
  logInfo(`UI: showStep(${s})`);

  // Toggle step panels
  document.querySelectorAll(".b2s-step").forEach((el) => {
    el.classList.toggle("active", Number(el.dataset.step) === s);
  });

  updateStepperUI();
  updateProgress();
}

export function nextStep() {
  showStep(Math.min(currentStep + 1, STEPS.length));
}

export function prevStep() {
  showStep(Math.max(currentStep - 1, 1));
}

export function updateStepperUI() {
  document.querySelectorAll(".b2s-stepper li").forEach((li) => {
    const s = Number(li.dataset.step);
    li.classList.toggle("active", s === currentStep);
    li.classList.toggle("done", !!stepStatus[s]);
  });
}

export function updateProgress() {
  const idx = STEPS.indexOf(currentStep);
  const pct = (idx / (STEPS.length - 1)) * 100;

  const bar = document.getElementById("b2s_progress_bar");
  const label = document.getElementById("b2s_progress_label");

  if (bar) bar.style.width = `${pct}%`;
  if (label) label.textContent = `Étape ${idx + 1} sur ${STEPS.length}`;
}
