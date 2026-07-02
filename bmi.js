/* ============================================================
   bmi.js — BMI & TDEE Calculator page
   ============================================================ */

const calcBtn     = document.getElementById('calcBMIBtn');
const bmiResults  = document.getElementById('bmiResults');
const bmiHolder   = document.getElementById('bmiPlaceholder');

// Store last result for AI advice
let lastResult = null;

calcBtn?.addEventListener('click', async () => {
  const age      = parseInt(document.getElementById('bmiAge').value);
  const gender   = document.querySelector('input[name="bmiGender"]:checked')?.value || 'male';
  const weight   = parseFloat(document.getElementById('bmiWeight').value);
  const height   = parseFloat(document.getElementById('bmiHeight').value);
  const activity = document.getElementById('bmiActivity').value;
  const goal     = document.getElementById('bmiGoal').value;

  if (!age || !weight || !height) {
    alert('Please fill in age, weight, and height.');
    return;
  }

  calcBtn.disabled = true;
  calcBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Calculating…';

  try {
    const res  = await fetch('/api/bmi', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ age, gender, weight_kg: weight, height_cm: height, activity, goal }),
    });
    const data = await res.json();
    lastResult = { ...data, age, gender, weight, height, activity, goal };

    bmiHolder.classList.add('d-none');
    bmiResults.classList.remove('d-none');
    bmiResults.classList.add('slide-up');

    renderBMI(data.bmi);
    renderTDEE(data.tdee);
  } catch (err) {
    alert('Error calculating. Please try again.');
  } finally {
    calcBtn.disabled = false;
    calcBtn.innerHTML = '<i class="bi bi-calculator me-2"></i>Calculate';
  }
});

function renderBMI(bmi) {
  // Gauge arc animation
  const arc   = document.getElementById('bmiGaugeArc');
  const total = 251;
  const clamp = Math.min(40, Math.max(10, bmi.bmi));
  const pct   = (clamp - 10) / 30;
  setTimeout(() => {
    arc.style.strokeDashoffset  = total * (1 - pct);
    arc.style.transition        = 'stroke-dashoffset .8s ease';
  }, 100);
  document.getElementById('bmiGaugeValue').textContent = bmi.bmi;

  // Badge
  const badge = document.getElementById('bmiCategoryBadge');
  badge.textContent = bmi.category;
  const colorMap = { success:'bg-success', warning:'bg-warning', danger:'bg-danger', info:'bg-info' };
  badge.className  = `badge fs-6 px-3 py-2 ${colorMap[bmi.color] || 'bg-secondary'}`;

  document.getElementById('bmiValueDisplay').textContent = bmi.bmi;
  document.getElementById('bmiAdviceText').textContent   = bmi.advice;

  // Scale marker (BMI 10–40 → 0–100%)
  const markerPct = Math.min(98, Math.max(1, pct * 100));
  setTimeout(() => {
    document.getElementById('bmiMarker').style.left = markerPct + '%';
  }, 200);
}

function renderTDEE(tdee) {
  document.getElementById('bmrVal').textContent    = tdee.bmr.toLocaleString();
  document.getElementById('tdeeVal').textContent   = tdee.tdee.toLocaleString();
  document.getElementById('targetVal').textContent = tdee.target_calories.toLocaleString();
  document.getElementById('goalLabel').textContent = tdee.goal_label;

  // Water: ~35ml per kg bodyweight approx via weight stored in lastResult
  const water = lastResult ? (lastResult.weight * 0.033).toFixed(1) : '—';
  document.getElementById('waterVal').textContent = water;

  const m = tdee.macros;
  document.getElementById('proteinGrams').textContent = m.protein_g + 'g';
  document.getElementById('carbsGrams').textContent   = m.carbs_g   + 'g';
  document.getElementById('fatGrams').textContent     = m.fat_g     + 'g';
}

// ── AI Personalised Advice ────────────────────────────────────
document.getElementById('getAIAdviceBtn')?.addEventListener('click', async () => {
  if (!lastResult) { alert('Calculate your BMI first.'); return; }

  const area = document.getElementById('aiAdviceArea');
  area.innerHTML = '<div class="ai-spinner" style="width:28px;height:28px;border-width:3px;margin:auto"></div>';

  const prompt = `
My stats:
- Age: ${lastResult.age}, Gender: ${lastResult.gender}
- Weight: ${lastResult.weight}kg, Height: ${lastResult.height}cm
- BMI: ${lastResult.bmi?.bmi} (${lastResult.bmi?.category})
- TDEE: ${lastResult.tdee?.tdee} kcal/day
- Goal: ${lastResult.goal}
- Activity: ${lastResult.activity}

Based on my profile, give me:
1. A personalised nutrition strategy
2. Top 3 Indian food swaps to support my goal
3. One motivational tip
Keep it concise and actionable.`.trim();

  try {
    const res  = await fetch('/api/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: prompt }),
    });
    const data = await res.json();
    area.innerHTML = renderMarkdown(data.reply || 'Could not generate advice.');
  } catch (err) {
    area.textContent = 'Error fetching advice. Please try again.';
  }
});
