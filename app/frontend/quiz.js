let quizQuestions = [];

document.addEventListener('DOMContentLoaded', loadQuiz);

async function loadQuiz() {
    const courseContent = localStorage.getItem('currentCourse');
    if (!courseContent) {
        window.location.href = '/';
        return;
    }

    const container = document.getElementById('quiz-content');
    container.innerHTML = '<p>Generating quiz...</p>';

    try {
        const response = await fetch('/api/create_quiz', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ course_content: courseContent })
        });
        const data = await response.json();
        renderQuiz(data.questions || []);
    } catch (e) {
        container.innerHTML = '<p>Failed to load quiz. Please go back and try again.</p>';
    }
}

function renderQuiz(questions) {
    quizQuestions = questions;
    const container = document.getElementById('quiz-content');

    if (!questions.length) {
        container.innerHTML = '<p>No questions generated. Please go back and try again.</p>';
        return;
    }

    let html = '';
    questions.forEach((q, i) => {
        html += `<div class="question-card">
            <h3>${i + 1}. ${q.question}</h3>
            ${q.options.map(opt => `
                <label style="display:block;margin:6px 0;cursor:pointer;">
                    <input type="radio" name="q${i}" value="${opt}"> ${opt}
                </label>`).join('')}
        </div>`;
    });
    html += `<button class="submit-btn" id="submit-quiz">Submit Quiz</button>`;
    container.innerHTML = html;

    document.getElementById('submit-quiz').addEventListener('click', submitQuiz);
}

async function submitQuiz() {
    const answers = quizQuestions.map((_, i) => {
        const sel = document.querySelector(`input[name="q${i}"]:checked`);
        return sel ? sel.value : 'Not Answered';
    });

    const container = document.getElementById('quiz-content');
    container.innerHTML = '<p>Assessing your answers...</p>';

    try {
        const response = await fetch('/api/assess_quiz', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ questions: quizQuestions, answers })
        });
        const result = await response.json();
        renderResults(result, answers);
    } catch (e) {
        container.innerHTML = '<p>Failed to assess. Please try again.</p>';
    }
}

function renderResults(result, userAnswers) {
    const container = document.getElementById('quiz-content');

    const correctAnswers = result.correct_answers || quizQuestions.map(q => q.correct);

    const questionsHtml = quizQuestions.map((q, i) => {
        const isCorrect = userAnswers[i] === correctAnswers[i];
        return `<div class="result-card" style="border-left: 4px solid ${isCorrect ? '#22c55e' : '#ef4444'};padding-left:12px;margin-bottom:16px;">
            <strong>Q${i + 1}: ${q.question}</strong><br>
            Your answer: ${userAnswers[i]}<br>
            ${!isCorrect ? `<span style="color:#22c55e">Correct: ${correctAnswers[i]}</span>` : '<span style="color:#22c55e">✓ Correct!</span>'}
        </div>`;
    }).join('');

    container.innerHTML = `
        <div style="text-align:center;margin-bottom:32px;padding:24px;background:#f8fafc;border-radius:16px;">
            <h2 style="font-size:3rem;margin:0;">${result.grade || 'N/A'}</h2>
            <p style="font-size:1.5rem;margin:8px 0;">${result.score}/${result.total} — ${result.percentage?.toFixed(0) ?? 0}%</p>
            <p style="color:#64748b;max-width:500px;margin:0 auto;">${result.feedback || ''}</p>
        </div>
        ${questionsHtml}
        <button class="submit-btn" onclick="window.location.href='/'">Back to Home</button>
    `;
}
