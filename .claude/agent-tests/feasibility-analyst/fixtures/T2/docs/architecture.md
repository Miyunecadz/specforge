# Procurement platform notes

Awards are stored in the procurement service's `awards` table (one row per package).
Supplier emails are sent through the internal NotifyHub service, which reports delivery failures by webhook.
There is no audit log today.
