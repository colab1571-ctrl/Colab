output "daily_budget_name" {
  value       = aws_budgets_budget.daily.name
  description = "Name of the daily cost budget."
}

output "monthly_forecast_budget_name" {
  value       = aws_budgets_budget.monthly_forecast.name
  description = "Name of the monthly forecasted budget."
}
