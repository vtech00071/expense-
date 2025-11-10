// ### NEW FUNCTION TO FORMAT CURRENCY ###
function formatCurrency(number) {
    // This creates a number formatter for US English, which uses
    // commas for thousands and dots for decimals.
    const formatter = new Intl.NumberFormat('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
    return formatter.format(number);
}
// ### END OF NEW FUNCTION ###

document.addEventListener("DOMContentLoaded", () => {
    // === DOM Elements ===
    const totalBalanceEl = document.getElementById("totalBalance");
    const totalIncomeEl = document.getElementById("totalIncome");
    const totalExpensesEl = document.getElementById("totalExpenses");
    const addExpenseForm = document.getElementById("addExpenseForm");
    const recentTransactionsList = document.getElementById("recentTransactionsList");
    const setBudgetForm = document.getElementById("setBudgetForm");
    const budgetList = document.getElementById("budgetList");
    const resetButton = document.getElementById('reset-btn');
    const addGoalForm = document.getElementById("addGoalForm");
    const goalsList = document.getElementById("goalsList");
    const fundGoalModal = document.getElementById("fundGoalModal");
    const fundGoalForm = document.getElementById("fundGoalForm");
    const fundGoalSelect = document.getElementById("fundGoalSelect");

    let spendingChart;

    // === Modal Logic ===
    const alertModal = document.getElementById('alertModal');
    const modalMessage = document.getElementById('modalMessage');
    const modalCloseButtons = document.querySelectorAll('.modal-close-btn');

    function showModal(message) {
        modalMessage.textContent = message;
        alertModal.style.display = 'flex';
    }

    modalCloseButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            alertModal.style.display = 'none';
        });
    });

    // === Core Data Fetching & UI Rendering ===
    async function fetchDashboardData() {
        try {
            const res = await fetch("/get_dashboard_data");
            const data = await res.json();
            if (data.status === "success") {
                // ### UPDATED WITH formatCurrency ###
                totalBalanceEl.textContent = `₦${formatCurrency(data.total_balance)}`;
                totalIncomeEl.textContent = `₦${formatCurrency(data.total_income)}`;
                totalExpensesEl.textContent = `₦${formatCurrency(data.total_expenses)}`;
                
                updateSpendingChart(data.spending_by_category);
                displayBudgets(data.budgets, data.spending_by_category);
            }
        } catch (error) {
            console.error("Error fetching dashboard data:", error);
        }
    }
    
    async function fetchAndDisplayTransactions() {
        try {
            const res = await fetch("/get_all_transactions");
            const data = await res.json();
            if (data.status === "success") {
                recentTransactionsList.innerHTML = "";
                if (data.transactions.length === 0) {
                    recentTransactionsList.innerHTML = `<p class="no-data-message">No transactions yet.</p>`;
                } else {
                    data.transactions.forEach(transaction => {
                        const transactionDiv = document.createElement("div");
                        const isExpense = transaction.type === 'expense';
                        transactionDiv.classList.add("transaction-item", isExpense ? "expense-item" : "income-item");
                        
                        // ### UPDATED WITH formatCurrency ###
                        const amountText = isExpense ? 
                            `<span class="transaction-amount">-₦${formatCurrency(transaction.amount)}</span>` :
                            `<span class="transaction-amount">+₦${formatCurrency(transaction.amount)}</span>`;
                        
                        const transactionIcon = isExpense ? 
                            `<i class="fas fa-arrow-down transaction-icon"></i>` :
                            `<i class="fas fa-arrow-up transaction-icon"></i>`;
                        
                        transactionDiv.innerHTML = `
                            <div class="transaction-details">
                                ${transactionIcon}
                                <div class="transaction-info">
                                    <span class="transaction-description">${transaction.description || transaction.category || 'Income'}</span>
                                    <span class="transaction-date">${transaction.date}</span>
                                </div>
                            </div>
                            ${amountText}
                        `;
                        recentTransactionsList.appendChild(transactionDiv);
                    });
                }
            } else {
                recentTransactionsList.innerHTML = `<p>${data.message}</p>`;
            }
        } catch (error) {
            console.error("Error fetching transactions:", error);
        }
    }
    
    function updateSpendingChart(spendingData) {
        const ctx = document.getElementById("spendingChart").getContext("2d");
        const labels = Object.keys(spendingData);
        const amounts = Object.values(spendingData);

        if (spendingChart) {
            spendingChart.destroy();
        }

        spendingChart = new Chart(ctx, {
            type: 'pie',
            data: {
                labels: labels,
                datasets: [{
                    data: amounts,
                    backgroundColor: [
                        '#4F46E5', '#10B981', '#EF4444', '#F59E0B', '#6366F1', '#D8B4FE'
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'top' },
                    title: { display: false }
                }
            }
        });
    }

    function displayBudgets(budgets, spending) {
        budgetList.innerHTML = "";
        let hasBudgets = false;
        for (const category in budgets) {
            if (Object.prototype.hasOwnProperty.call(budgets, category)) {
                hasBudgets = true;
                const budgetAmount = budgets[category];
                const spentAmount = spending[category] || 0;
                
                // Ensure budgetAmount is not zero to avoid division by zero
                const progress = budgetAmount > 0 ? (spentAmount / budgetAmount) * 100 : 0;
                
                const budgetItem = document.createElement("div");
                budgetItem.classList.add("budget-item");
                
                const progressClass = progress > 100 ? "over" : "";
                
                // ### UPDATED WITH formatCurrency ###
                budgetItem.innerHTML = `
                    <div class="budget-info">
                        <span class="budget-category-label">${category}</span>
                        <span class="budget-amounts">₦${formatCurrency(spentAmount)} / ₦${formatCurrency(budgetAmount)}</span>
                    </div>
                    <div class="budget-progress-bar">
                        <div class="budget-progress ${progressClass}" style="width: ${Math.min(progress, 100)}%;"></div>
                    </div>
                `;
                budgetList.appendChild(budgetItem);
            }
        }
        if (!hasBudgets) {
            budgetList.innerHTML = `<p class="no-data-message">No budgets set yet.</p>`;
        }
    }

    async function fetchAndDisplayGoals() {
        try {
            const res = await fetch("/get_goals");
            const data = await res.json();

            goalsList.innerHTML = "";
            if (data.status === "success" && data.goals.length > 0) {
                fundGoalSelect.innerHTML = data.goals.map(goal => 
                    `<option value="${goal.id}">${goal.name}</option>`
                ).join('');

                data.goals.forEach(goal => {
                    const goalItem = document.createElement("div");
                    goalItem.classList.add("budget-item");
                    
                    const progress = (goal.current_amount / goal.target_amount) * 100;
                    const progressClass = progress >= 100 ? "over" : "";
                    
                    // ### UPDATED WITH formatCurrency ###
                    goalItem.innerHTML = `
                        <div class="budget-info">
                            <span class="budget-category-label">${goal.name}</span>
                            <span class="budget-amounts">₦${formatCurrency(goal.current_amount)} / ₦${formatCurrency(goal.target_amount)}</span>
                        </div>
                        <div class="budget-progress-bar">
                            <div class="budget-progress ${progressClass}" style="width: ${Math.min(progress, 100)}%;"></div>
                        </div>
                        <button class="btn btn-primary add-fund-btn" data-goal-id="${goal.id}" data-goal-name="${goal.name}"><i class="fas fa-coins"></i> Add Funds</button>
                    `;
                    goalsList.appendChild(goalItem);
                });
            } else {
                goalsList.innerHTML = `<p class="no-data-message">No goals set yet.</p>`;
            }
        } catch (error) {
            console.error("Error fetching goals:", error);
            goalsList.innerHTML = `<p class="no-data-message">Error loading goals.</p>`;
        }
    }

    // === Event Listeners for Forms and Buttons ===

    document.addEventListener("click", (e) => {
        if (e.target.classList.contains("add-fund-btn")) {
            fundGoalModal.style.display = 'flex';
        }
    });

    if (fundGoalForm) {
        fundGoalForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const form = e.target;
            try {
                const res = await fetch("/add_to_goal", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        goal_id: parseInt(form.fundGoalSelect.value),
                        amount: parseFloat(form.fundAmount.value)
                    })
                });
                const data = await res.json();
                showModal(data.message);
                if (data.status === "success") {
                    form.reset();
                    fundGoalModal.style.display = 'none';
                    fetchAndDisplayGoals();
                    fetchDashboardData();
                }
            } catch (error) {
                showModal('An error occurred. Please try again.');
            }
        });
    }

    if(fundGoalModal) {
        fundGoalModal.addEventListener('click', (e) => {
            if (e.target === fundGoalModal || e.target.classList.contains('modal-close-btn')) {
                fundGoalModal.style.display = 'none';
            }
        });
    }

    if (addExpenseForm) {
        addExpenseForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const form = e.target;
            
            try {
                const res = await fetch("/add_expense", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        amount: parseFloat(form.expenseAmount.value),
                        category: form.expenseCategory.value,
                        description: form.expenseDescription.value,
                        date: form.expenseDate.value
                    })
                });
                
                const data = await res.json();
                showModal(data.message); // This will show the "Budget Exceeded!" error
                
                if (data.status === "success") {
                    form.reset();
                    fetchDashboardData();
                    fetchAndDisplayTransactions();
                }
            } catch (error) {
                showModal('An error occurred. Please try again.');
            }
        });
    }
    
    if (setBudgetForm) {
        setBudgetForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const form = e.target;
            try {
                const res = await fetch("/set_budget", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        category: form.budgetCategory.value,
                        amount: parseFloat(form.budgetAmount.value)
                    })
                });
                const data = await res.json();
                showModal(data.message); // This will show "Insufficient Balance!" error
                if (data.status === "success") {
                    form.reset();
                    fetchDashboardData();
                }
            } catch(error) {
                showModal('An error occurred. Please try again.');
            }
        });
    }

    if (addGoalForm) {
        addGoalForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const form = e.target;
            try {
                const res = await fetch("/add_goal", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        name: form.goalName.value,
                        target_amount: parseFloat(form.goalTargetAmount.value)
                    })
                });
                const data = await res.json();
                showModal(data.message);
                if (data.status === "success") {
                    form.reset();
                    fetchAndDisplayGoals();
                }
            } catch (error) {
                showModal('An error occurred. Please try again.');
            }
        });
    }

    if (resetButton) {
        resetButton.addEventListener('click', async (e) => {
            e.preventDefault();
            
            const isConfirmed = confirm("Are you sure you want to reset all your financial data? This action cannot be undone.");
            
            if (isConfirmed) {
                try {
                    const res = await fetch("/reset_data", {
                        method: "POST"
                    });
                    const data = await res.json();
                    
                    if (data.status === "success") {
                        showModal(data.message);
                        setTimeout(() => {
                            location.reload(); 
                        }, 2000);
                    } else {
                        showModal(data.message);
                    }
                } catch (error) {
                    showModal('An error occurred during the reset process.');
                }
            }
        });
    }

    // ### --- THIS IS THE PAYSTACK LOGIC for the "Add Income" form --- ###
    const fundAccountForm = document.getElementById("fundAccountForm"); // This is now the "Add Income" form
    if (fundAccountForm) {
        fundAccountForm.addEventListener("submit", (e) => {
            e.preventDefault();
            
            const amount = parseFloat(document.getElementById("fundAmountInput").value);
            const amountInKobo = Math.round(amount * 100); // Convert to kobo
            const userEmail = document.body.dataset.userEmail; // Get email from body tag

            if (isNaN(amountInKobo) || amountInKobo <= 0) {
                showModal("Please enter a valid amount.");
                return;
            }

            let handler = PaystackPop.setup({
                key: 'pk_test_8bddf748c972f5a1e15bb43e42741645ca8ac8f6', // Your Public Key
                email: userEmail,
                amount: amountInKobo,
                currency: 'NGN',
                ref: 'expense-tracker-' + Math.floor((Math.random() * 1000000000) + 1),
                
                callback: function(response) {
                    // Redirect to our backend to verify the payment
                    window.location.href = '/payment/callback?reference=' + response.reference;
                },
                onClose: function() {
                    showModal('Payment window closed.');
                }
            });
            handler.openIframe();
        });
    }
    
    // === Initial Data Load ===
    fetchDashboardData();
    fetchAndDisplayTransactions();
    fetchAndDisplayGoals();
});