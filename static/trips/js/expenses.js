let dailyExpenseChartInstance = null;
let categoryExpenseChartInstance = null;


document.addEventListener("DOMContentLoaded", () => {
    loadExpenseSummary();
    loadExpenseHistory();
    initializeExpenseForm();
});

function expenseGetCookie(name) {
    let cookieValue = null;

    if (document.cookie && document.cookie !== "") {
        const cookies = document.cookie.split(";");

        for (let cookie of cookies) {
            cookie = cookie.trim();

            if (cookie.startsWith(name + "=")) {
                cookieValue = decodeURIComponent(
                    cookie.substring(name.length + 1)
                );
                break;
            }
        }
    }

    return cookieValue;
}

function formatExpenseCurrency(amount) {
    return new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: 2
    }).format(amount || 0);
}

async function loadExpenseSummary() {
    try {
        const response = await fetch(
            `/trips/api/expense-summary/?trip_id=${encodeURIComponent(window.TRIP_ID)}`
        );

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.error || "Unable to load expense summary.");
        }

        const summary = data.summary;

        document.getElementById("expenseBudget").textContent =
            formatExpenseCurrency(summary.budget);

        document.getElementById("expenseSpent").textContent =
            formatExpenseCurrency(summary.total_spent);

            const remainingElement = document.getElementById("expenseRemaining");
            const percentageElement = document.getElementById("expensePercentage");
            
            remainingElement.textContent =
                formatExpenseCurrency(summary.remaining_budget);
            
            percentageElement.textContent =
                `${summary.budget_used_percentage}%`;
            
            const overBudget = summary.remaining_budget < 0;
            
            remainingElement.style.color = overBudget ? "#dc2626" : "";
            percentageElement.style.color = overBudget ? "#dc2626" : "";
            
            let warning = document.getElementById("budgetWarning");
            
            if (!warning) {
                warning = document.createElement("p");
                warning.id = "budgetWarning";
                warning.style.fontWeight = "600";
            
                document.getElementById("expenseRemaining")
                    .parentElement.appendChild(warning);
            }
            
            if (overBudget) {
                warning.textContent =
                    `⚠ Over budget by ${formatExpenseCurrency(Math.abs(summary.remaining_budget))}`;
                warning.style.color = "#dc2626";
            } else {
                warning.textContent = "";
            }

        renderExpenseCharts(summary);

    } catch (error) {
        console.error("Expense summary error:", error);
        alert(error.message);
    }
}

// Initialize Add Expense form.
function initializeExpenseForm() {
    const form = document.getElementById("expenseForm");

    if (!form) return;

    form.addEventListener("submit", async (event) => {
        event.preventDefault();

        const messageElement = document.getElementById("expenseFormMessage");

        if (messageElement) {
            messageElement.hidden = true;
            messageElement.textContent = "";
        }
        const amount = document.getElementById("expenseAmount").value;
        const category = document.getElementById("expenseCategory").value;
        const expenseDate = document.getElementById("expenseDate").value;
        const dayValue = document.getElementById("expenseDay").value;
        const description = document.getElementById("expenseDescription").value.trim();

        if (!amount || Number(amount) <= 0) {
            alert("Please enter a valid expense amount.");
            return;
        }

        if (!category || !expenseDate) {
            alert("Please complete all required fields.");
            return;
        }

        const payload = {
            trip_id: window.TRIP_ID,
            amount: amount,
            category: category,
            expense_date: expenseDate,
            day_number: dayValue ? Number(dayValue) : null,
            description: description
        };

        const submitButton = document.getElementById("addExpenseButton");
        submitButton.disabled = true;
        submitButton.textContent = "Saving...";

        try {
            const response = await fetch("/trips/api/add-expense/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": expenseGetCookie("csrftoken")
                },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (!response.ok || !data.success) {
                throw new Error(data.error || "Unable to save expense.");
            }

            alert("Expense added successfully!");

            form.reset();

            await loadExpenseSummary();
            await loadExpenseHistory();

            const details = document.querySelector(".expense-form-toggle");
            if (details) details.open = false;

        } catch (error) {
            console.error("Add expense error:", error);
        
            showExpenseFormMessage(error.message, "error");

        } finally {
            submitButton.disabled = false;
            submitButton.textContent = "Save Expense";
        }
    });
}

// Load and display expense history.

async function loadExpenseHistory() {
    const historyContainer = document.getElementById("expenseHistory");

    if (!historyContainer) return;

    try {
        const response = await fetch(
            `/trips/api/expense-summary/?trip_id=${encodeURIComponent(window.TRIP_ID)}`
        );

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.error || "Unable to load expense history.");
        }

        const expenses = data.summary.expenses || [];

        if (expenses.length === 0) {
            historyContainer.innerHTML =
                "<p>No expenses recorded yet.</p>";
            return;
        }

        
historyContainer.innerHTML = `
<div class="expense-table-wrapper">
    <table class="expense-table">
        <thead>
            <tr>
                <th>Date</th>
                <th>Category</th>
                <th>Description</th>
                <th>Day</th>
                <th>Amount</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            ${expenses.map(expense => `
                <tr>
                    <td>${escapeExpenseHTML(expense.expense_date)}</td>
                    <td>
                        <span class="expense-category">
                            ${escapeExpenseHTML(expense.category)}
                        </span>
                    </td>
                    <td>${escapeExpenseHTML(expense.description || "—")}</td>
                    <td>${expense.day_number ? `Day ${Number(expense.day_number)}` : "—"}</td>
                    <td class="expense-amount">
                        ${formatExpenseCurrency(expense.amount)}
                    </td>
                    <td>
                        <button type="button"
                            class="edit-expense-button"
                            data-expense-id="${escapeExpenseHTML(expense.expense_id)}">
                            Edit
                        </button>
                        <button type="button"
                            class="delete-expense-button"
                            data-expense-id="${escapeExpenseHTML(expense.expense_id)}">
                            Delete
                        </button>
                    </td>
                </tr>
            `).join("")}
        </tbody>
    </table>
</div>
`;


    } catch (error) {
        console.error("Expense history error:", error);
        historyContainer.innerHTML =
            "<p>Unable to load expense history.</p>";
    }
}


// Escape user-provided text before inserting it into HTML.
function escapeExpenseHTML(value) {
    return String(value).replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
    })[character]);
}



function renderExpenseCharts(summary) {
    if (typeof Chart === "undefined") {
        console.error("Chart.js is not loaded.");
        return;
    }

    // Daily Spending Chart
    const dailyCanvas = document.getElementById("dailyExpenseChart");

    if (dailyCanvas) {
        if (dailyExpenseChartInstance) {
            dailyExpenseChartInstance.destroy();
        }

        const dailyData = summary.daily_totals || {};
        const dailyLabels = Object.keys(dailyData);
        const dailyValues = Object.values(dailyData);

        dailyExpenseChartInstance = new Chart(dailyCanvas, {
            type: "bar",
            data: {
                labels: dailyLabels,
                datasets: [{
                    label: "Daily Spending (₹)",
                    data: dailyValues,
                    borderRadius: 6,
                    backgroundColor: "#287a57"
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: value => "₹" + value
                        }
                    }
                }
            }
        });
    }

    // Category-wise Spending Chart
    const categoryCanvas = document.getElementById("categoryExpenseChart");

    if (categoryCanvas) {
        if (categoryExpenseChartInstance) {
            categoryExpenseChartInstance.destroy();
        }

        const categoryData = summary.category_totals || {};

        categoryExpenseChartInstance = new Chart(categoryCanvas, {
            type: "doughnut",
            data: {
                labels: Object.keys(categoryData),
                datasets: [{
                    data: Object.values(categoryData),
                    backgroundColor: [
                        "#287a57",
                        "#e5a33d",
                        "#4986c6",
                        "#9b70bd",
                        "#df7373",
                        "#8b969e"
                    ],
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "bottom"
                    }
                }
            }
        });
    }
}


function showExpenseFormMessage(message, type = "error") {
    const messageElement = document.getElementById("expenseFormMessage");

    if (!messageElement) return;

    messageElement.textContent = message;
    messageElement.className = `expense-form-message ${type}`;
    messageElement.hidden = false;
}



// Expense Edit Modal and Delete Functionality

document.addEventListener("DOMContentLoaded", () => {

    const historyContainer = document.getElementById("expenseHistory");
    const modal = document.getElementById("editExpenseModal");
    const editForm = document.getElementById("editExpenseForm");

    if (!historyContainer || !modal || !editForm) return;

    let currentExpenseId = null;

    function closeEditModal() {
        modal.hidden = true;
        editForm.reset();
        currentExpenseId = null;

        const message = document.getElementById("editExpenseMessage");
        message.hidden = true;
        message.textContent = "";
    }

    function showEditMessage(message, type = "error") {
        const element = document.getElementById("editExpenseMessage");
        element.textContent = message;
        element.className = `expense-form-message ${type}`;
        element.hidden = false;
    }

    // Open edit modal and populate existing values.
    historyContainer.addEventListener("click", async (event) => {

        const editButton = event.target.closest(".edit-expense-button");
        const deleteButton = event.target.closest(".delete-expense-button");

        if (editButton) {
            try {
                const expenseId = editButton.dataset.expenseId;

                const response = await fetch(
                    `/trips/api/expense-summary/?trip_id=${encodeURIComponent(window.TRIP_ID)}`
                );

                const data = await response.json();

                if (!response.ok || !data.success) {
                    throw new Error(data.error || "Unable to load expense.");
                }

                const expense = data.summary.expenses.find(
                    item => item.expense_id === expenseId
                );

                if (!expense) {
                    throw new Error("Expense not found.");
                }

                currentExpenseId = expenseId;

                document.getElementById("editExpenseAmount").value =
                    expense.amount;

                document.getElementById("editExpenseCategory").value =
                    expense.category;

                document.getElementById("editExpenseDate").value =
                    expense.expense_date;

                document.getElementById("editExpenseDescription").value =
                    expense.description || "";

                document.getElementById("editExpenseDay").value =
                    expense.day_number ?? "";

                modal.hidden = false;

            } catch (error) {
                alert(error.message);
            }
        }

        // Delete expense.
        if (deleteButton) {
            const expenseId = deleteButton.dataset.expenseId;

            if (!confirm("Are you sure you want to delete this expense?")) {
                return;
            }

            try {
                const response = await fetch("/trips/api/delete-expense/", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": expenseGetCookie("csrftoken")
                    },
                    body: JSON.stringify({
                        trip_id: window.TRIP_ID,
                        expense_id: expenseId
                    })
                });

                const data = await response.json();

                if (!response.ok || !data.success) {
                    throw new Error(data.error || "Unable to delete expense.");
                }

                await loadExpenseSummary();
                await loadExpenseHistory();

            } catch (error) {
                alert(error.message);
            }
        }
    });

    // Save edited expense.
    editForm.addEventListener("submit", async (event) => {
        event.preventDefault();

        const amount = document.getElementById("editExpenseAmount").value;
        const category = document.getElementById("editExpenseCategory").value;
        const expenseDate = document.getElementById("editExpenseDate").value;
        const dayValue = document.getElementById("editExpenseDay").value;
        const description = document.getElementById("editExpenseDescription").value.trim();

        if (!amount || !Number.isFinite(Number(amount)) || Number(amount) <= 0) {
            showEditMessage("Please enter a valid expense amount.");
            return;
        }

        if (!category || !expenseDate) {
            showEditMessage("Please complete all required fields.");
            return;
        }

        const selectedDay = document.querySelector(
            `#editExpenseDay option[value="${dayValue}"]`
        );

        if (dayValue && selectedDay.dataset.date !== expenseDate) {
            showEditMessage(
                "The selected itinerary day does not match the expense date. Please select the correct day or choose 'Not linked to a day'."
            );
            return;
        }

        const saveButton = document.getElementById("saveExpenseChanges");
        saveButton.disabled = true;
        saveButton.textContent = "Saving...";

        try {
            const response = await fetch("/trips/api/update-expense/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": expenseGetCookie("csrftoken")
                },
                body: JSON.stringify({
                    trip_id: window.TRIP_ID,
                    expense_id: currentExpenseId,
                    amount: amount,
                    category: category,
                    description: description,
                    expense_date: expenseDate,
                    day_number: dayValue ? Number(dayValue) : null
                })
            });

            const data = await response.json();

            if (!response.ok || !data.success) {
                throw new Error(data.error || "Unable to update expense.");
            }

            closeEditModal();

            await loadExpenseSummary();
            await loadExpenseHistory();

        } catch (error) {
            showEditMessage(error.message);

        } finally {
            saveButton.disabled = false;
            saveButton.textContent = "Save Changes";
        }
    });

    document.getElementById("closeExpenseModal")
        .addEventListener("click", closeEditModal);

    document.getElementById("cancelExpenseEdit")
        .addEventListener("click", closeEditModal);

    modal.addEventListener("click", (event) => {
        if (event.target === modal) {
            closeEditModal();
        }
    });

});
