XP
v 1 Register_FrontOffice
v 2 Check_BackOffice
v 3 Approve_Management
v 4 Notify_FrontOffice
e 1 2 Register_FrontOffice__Check_BackOffice
e 2 3 Check_BackOffice__Approve_Management
e 3 4 Approve_Management__Notify_FrontOffice

XP
v 1 Register_FrontOffice
v 2 Check_BackOffice
v 3 Approve_Management
v 4 Archive_BackOffice
e 1 2 Register_FrontOffice__Check_BackOffice
e 2 3 Check_BackOffice__Approve_Management
e 3 4 Approve_Management__Archive_BackOffice

XP
v 1 Register_FrontOffice
v 2 Check_BackOffice
v 3 Approve_Management
e 1 2 Register_FrontOffice__Check_BackOffice
e 2 3 Check_BackOffice__Approve_Management

XP
v 1 Register_FrontOffice
v 2 Check_BackOffice
v 3 Rework_BackOffice
v 4 Approve_Management
e 1 2 Register_FrontOffice__Check_BackOffice
e 2 3 Check_BackOffice__Rework_BackOffice
e 3 4 Rework_BackOffice__Approve_Management

XP
v 1 Register_FrontOffice
v 2 Check_BackOffice
v 3 Archive_BackOffice
e 1 2 Register_FrontOffice__Check_BackOffice
e 2 3 Check_BackOffice__Archive_BackOffice

