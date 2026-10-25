XP
v 1 start_User_1
v 2 A-Create-Application_User_1
v 3 A-Submitted_User_1
v 4 W-Handle-leads-schedule_User_1
v 5 W-Handle-leads-start_User_141
v 6 W-Handle-leads-suspend_User_2
v 7 W-Handle-leads-resume_User_25
v 8 W-Handle-leads-suspend_User_25
v 9 W-Handle-leads-resume_User_25
v 10 W-Handle-leads-complete_User_25
v 11 W-Complete-application-schedule_User_25
v 12 W-Complete-application-start_User_25
v 13 A-Concept_User_25
v 14 W-Complete-application-suspend_User_25
v 15 W-Complete-application-resume_User_5
v 16 W-Complete-application-suspend_User_5
v 17 W-Complete-application-resume_User_2
v 18 W-Complete-application-suspend_User_2
v 19 A-Accepted_User_16
v 20 O-Create-Offer_User_16
v 21 O-Created_User_16
v 22 O-Sent-mail-and-online_User_16
v 23 W-Complete-application-ate-abort_User_16
v 24 W-Call-after-offers-schedule_User_16
v 25 W-Call-after-offers-start_User_16
v 26 A-Complete_User_16
v 27 W-Call-after-offers-suspend_User_16
v 28 W-Call-after-offers-resume_User_18
v 29 W-Call-after-offers-suspend_User_18
v 30 O-Create-Offer_User_25
v 31 O-Created_User_25
v 32 W-Call-after-offers-ate-abort_User_120
v 33 W-Validate-application-schedule_User_120
v 34 W-Validate-application-start_User_120
v 35 A-Validating_User_120
v 36 O-Returned_User_120
v 37 W-Validate-application-suspend_User_120
v 38 W-Validate-application-resume_User_87
v 39 W-Validate-application-suspend_User_87
v 40 W-Validate-application-resume_User_21
v 41 W-Validate-application-suspend_User_21
v 42 W-Validate-application-resume_User_29
v 43 A-Denied_User_29
v 44 O-Refused_User_29
v 45 O-Refused_User_29
v 46 W-Validate-application-complete_User_29
v 47 end_User_29
e 5 6 W-Handle-leads-start_User_141__W-Handle-leads-suspend_User_2
e 6 7 W-Handle-leads-suspend_User_2__W-Handle-leads-resume_User_25
e 7 8 W-Handle-leads-resume_User_25__W-Handle-leads-suspend_User_25
e 8 9 W-Handle-leads-suspend_User_25__W-Handle-leads-resume_User_25
e 9 10 W-Handle-leads-resume_User_25__W-Handle-leads-complete_User_25
e 10 11 W-Handle-leads-complete_User_25__W-Complete-application-schedule_User_25
e 11 12 W-Complete-application-schedule_User_25__W-Complete-application-start_User_25
e 12 13 W-Complete-application-start_User_25__A-Concept_User_25
e 13 14 A-Concept_User_25__W-Complete-application-suspend_User_25
e 14 15 W-Complete-application-suspend_User_25__W-Complete-application-resume_User_5
e 15 16 W-Complete-application-resume_User_5__W-Complete-application-suspend_User_5
e 16 17 W-Complete-application-suspend_User_5__W-Complete-application-resume_User_2
e 17 18 W-Complete-application-resume_User_2__W-Complete-application-suspend_User_2
e 18 19 W-Complete-application-suspend_User_2__A-Accepted_User_16
e 19 20 A-Accepted_User_16__O-Create-Offer_User_16
e 20 21 O-Create-Offer_User_16__O-Created_User_16
e 21 22 O-Created_User_16__O-Sent-mail-and-online_User_16
e 22 23 O-Sent-mail-and-online_User_16__W-Complete-application-ate-abort_User_16
e 23 24 W-Complete-application-ate-abort_User_16__W-Call-after-offers-schedule_User_16
e 24 25 W-Call-after-offers-schedule_User_16__W-Call-after-offers-start_User_16
e 25 26 W-Call-after-offers-start_User_16__A-Complete_User_16
e 26 27 A-Complete_User_16__W-Call-after-offers-suspend_User_16
e 27 28 W-Call-after-offers-suspend_User_16__W-Call-after-offers-resume_User_18
e 28 29 W-Call-after-offers-resume_User_18__W-Call-after-offers-suspend_User_18
e 29 30 W-Call-after-offers-suspend_User_18__O-Create-Offer_User_25
e 30 31 O-Create-Offer_User_25__O-Created_User_25
e 31 32 O-Created_User_25__W-Call-after-offers-ate-abort_User_120
e 32 33 W-Call-after-offers-ate-abort_User_120__W-Validate-application-schedule_User_120
e 33 34 W-Validate-application-schedule_User_120__W-Validate-application-start_User_120
e 34 35 W-Validate-application-start_User_120__A-Validating_User_120
e 35 36 A-Validating_User_120__O-Returned_User_120
e 36 37 O-Returned_User_120__W-Validate-application-suspend_User_120
e 37 38 W-Validate-application-suspend_User_120__W-Validate-application-resume_User_87
e 38 39 W-Validate-application-resume_User_87__W-Validate-application-suspend_User_87
e 39 40 W-Validate-application-suspend_User_87__W-Validate-application-resume_User_21
e 40 41 W-Validate-application-resume_User_21__W-Validate-application-suspend_User_21
e 41 42 W-Validate-application-suspend_User_21__W-Validate-application-resume_User_29
e 42 43 W-Validate-application-resume_User_29__A-Denied_User_29
e 43 44 A-Denied_User_29__O-Refused_User_29
e 44 45 O-Refused_User_29__O-Refused_User_29
e 45 46 O-Refused_User_29__W-Validate-application-complete_User_29
e 46 47 W-Validate-application-complete_User_29__end_User_29
e 47 1 end_User_29__start_User_1

XP
v 1 start_User_29
v 2 A-Create-Application_User_29
v 3 W-Complete-application-schedule_User_29
v 4 W-Complete-application-start_User_29
v 5 A-Concept_User_29
v 6 A-Accepted_User_29
v 7 O-Create-Offer_User_29
v 8 O-Created_User_29
v 9 W-Complete-application-complete_User_29
v 10 W-Call-after-offers-schedule_User_29
v 11 W-Call-after-offers-start_User_29
v 12 A-Complete_User_29
v 13 W-Call-after-offers-complete_User_29
v 14 W-Validate-application-schedule_User_29
v 15 W-Validate-application-start_User_29
v 16 A-Validating_User_29
v 17 O-Returned_User_29
v 18 W-Validate-application-complete_User_29
v 19 W-Call-incomplete-files-schedule_User_29
v 20 W-Call-incomplete-files-start_User_29
v 21 A-Incomplete_User_29
v 22 W-Call-incomplete-files-suspend_User_29
v 23 W-Call-incomplete-files-resume_User_49
v 24 W-Call-incomplete-files-suspend_User_49
v 25 W-Call-incomplete-files-resume_User_14
v 26 W-Call-incomplete-files-suspend_User_14
v 27 W-Call-incomplete-files-resume_User_38
v 28 W-Call-incomplete-files-suspend_User_38
v 29 W-Call-incomplete-files-resume_User_49
v 30 W-Call-incomplete-files-suspend_User_49
v 31 W-Call-incomplete-files-ate-abort_User_116
v 32 W-Validate-application-schedule_User_116
v 33 W-Validate-application-start_User_116
v 34 A-Validating_User_116
v 35 W-Validate-application-suspend_User_116
v 36 W-Validate-application-ate-abort_User_99
v 37 W-Call-incomplete-files-schedule_User_99
v 38 W-Call-incomplete-files-start_User_99
v 39 A-Incomplete_User_99
v 40 W-Call-incomplete-files-suspend_User_99
v 41 W-Call-incomplete-files-resume_User_13
v 42 W-Call-incomplete-files-suspend_User_13
v 43 W-Call-incomplete-files-ate-abort_User_120
v 44 W-Validate-application-schedule_User_120
v 45 W-Validate-application-start_User_120
v 46 A-Validating_User_120
v 47 W-Validate-application-suspend_User_120
v 48 W-Validate-application-resume_User_99
v 49 W-Validate-application-suspend_User_99
v 50 W-Validate-application-ate-abort_User_99
v 51 W-Call-incomplete-files-schedule_User_99
v 52 W-Call-incomplete-files-start_User_99
v 53 A-Incomplete_User_99
v 54 W-Call-incomplete-files-suspend_User_99
v 55 W-Call-incomplete-files-resume_User_92
v 56 W-Call-incomplete-files-suspend_User_92
v 57 W-Call-incomplete-files-ate-abort_User_113
v 58 W-Validate-application-schedule_User_113
v 59 W-Validate-application-start_User_113
v 60 A-Validating_User_113
v 61 W-Validate-application-suspend_User_113
v 62 W-Validate-application-resume_User_99
v 63 W-Validate-application-complete_User_99
v 64 W-Call-incomplete-files-schedule_User_99
v 65 W-Call-incomplete-files-start_User_99
v 66 A-Incomplete_User_99
v 67 W-Call-incomplete-files-suspend_User_99
v 68 W-Call-incomplete-files-resume_User_23
v 69 W-Call-incomplete-files-suspend_User_23
v 70 W-Call-incomplete-files-resume_User_23
v 71 W-Call-incomplete-files-suspend_User_23
v 72 W-Call-incomplete-files-resume_User_43
v 73 W-Call-incomplete-files-suspend_User_43
v 74 W-Call-incomplete-files-resume_User_23
v 75 W-Call-incomplete-files-suspend_User_23
v 76 W-Call-incomplete-files-resume_User_23
v 77 W-Validate-application-schedule_User_23
v 78 W-Validate-application-start_User_23
v 79 A-Validating_User_23
v 80 W-Validate-application-suspend_User_23
v 81 W-Validate-application-resume_User_99
v 82 A-Denied_User_99
v 83 O-Refused_User_99
v 84 W-Validate-application-complete_User_99
v 85 end_User_99
e 1 2 start_User_29__A-Create-Application_User_29
e 2 3 A-Create-Application_User_29__W-Complete-application-schedule_User_29
e 3 4 W-Complete-application-schedule_User_29__W-Complete-application-start_User_29
e 4 5 W-Complete-application-start_User_29__A-Concept_User_29
e 5 6 A-Concept_User_29__A-Accepted_User_29
e 6 7 A-Accepted_User_29__O-Create-Offer_User_29
e 7 8 O-Create-Offer_User_29__O-Created_User_29
e 8 9 O-Created_User_29__W-Complete-application-complete_User_29
e 9 10 W-Complete-application-complete_User_29__W-Call-after-offers-schedule_User_29
e 10 11 W-Call-after-offers-schedule_User_29__W-Call-after-offers-start_User_29
e 11 12 W-Call-after-offers-start_User_29__A-Complete_User_29
e 12 13 A-Complete_User_29__W-Call-after-offers-complete_User_29
e 13 14 W-Call-after-offers-complete_User_29__W-Validate-application-schedule_User_29
e 14 15 W-Validate-application-schedule_User_29__W-Validate-application-start_User_29
e 15 16 W-Validate-application-start_User_29__A-Validating_User_29
e 16 17 A-Validating_User_29__O-Returned_User_29
e 17 18 O-Returned_User_29__W-Validate-application-complete_User_29
e 18 19 W-Validate-application-complete_User_29__W-Call-incomplete-files-schedule_User_29
e 19 20 W-Call-incomplete-files-schedule_User_29__W-Call-incomplete-files-start_User_29
e 20 21 W-Call-incomplete-files-start_User_29__A-Incomplete_User_29
e 21 22 A-Incomplete_User_29__W-Call-incomplete-files-suspend_User_29
e 22 23 W-Call-incomplete-files-suspend_User_29__W-Call-incomplete-files-resume_User_49
e 23 24 W-Call-incomplete-files-resume_User_49__W-Call-incomplete-files-suspend_User_49
e 24 25 W-Call-incomplete-files-suspend_User_49__W-Call-incomplete-files-resume_User_14
e 25 26 W-Call-incomplete-files-resume_User_14__W-Call-incomplete-files-suspend_User_14
e 26 27 W-Call-incomplete-files-suspend_User_14__W-Call-incomplete-files-resume_User_38
e 27 28 W-Call-incomplete-files-resume_User_38__W-Call-incomplete-files-suspend_User_38
e 28 29 W-Call-incomplete-files-suspend_User_38__W-Call-incomplete-files-resume_User_49
e 29 30 W-Call-incomplete-files-resume_User_49__W-Call-incomplete-files-suspend_User_49
e 30 31 W-Call-incomplete-files-suspend_User_49__W-Call-incomplete-files-ate-abort_User_116
e 31 32 W-Call-incomplete-files-ate-abort_User_116__W-Validate-application-schedule_User_116
e 32 33 W-Validate-application-schedule_User_116__W-Validate-application-start_User_116
e 33 34 W-Validate-application-start_User_116__A-Validating_User_116
e 34 35 A-Validating_User_116__W-Validate-application-suspend_User_116
e 35 36 W-Validate-application-suspend_User_116__W-Validate-application-ate-abort_User_99
e 36 37 W-Validate-application-ate-abort_User_99__W-Call-incomplete-files-schedule_User_99
e 37 38 W-Call-incomplete-files-schedule_User_99__W-Call-incomplete-files-start_User_99
e 38 39 W-Call-incomplete-files-start_User_99__A-Incomplete_User_99
e 39 40 A-Incomplete_User_99__W-Call-incomplete-files-suspend_User_99
e 40 41 W-Call-incomplete-files-suspend_User_99__W-Call-incomplete-files-resume_User_13
e 41 42 W-Call-incomplete-files-resume_User_13__W-Call-incomplete-files-suspend_User_13
e 42 43 W-Call-incomplete-files-suspend_User_13__W-Call-incomplete-files-ate-abort_User_120
e 43 44 W-Call-incomplete-files-ate-abort_User_120__W-Validate-application-schedule_User_120
e 44 45 W-Validate-application-schedule_User_120__W-Validate-application-start_User_120
e 45 46 W-Validate-application-start_User_120__A-Validating_User_120
e 46 47 A-Validating_User_120__W-Validate-application-suspend_User_120
e 47 48 W-Validate-application-suspend_User_120__W-Validate-application-resume_User_99
e 48 49 W-Validate-application-resume_User_99__W-Validate-application-suspend_User_99
e 49 50 W-Validate-application-suspend_User_99__W-Validate-application-ate-abort_User_99
e 50 51 W-Validate-application-ate-abort_User_99__W-Call-incomplete-files-schedule_User_99
e 51 52 W-Call-incomplete-files-schedule_User_99__W-Call-incomplete-files-start_User_99
e 52 53 W-Call-incomplete-files-start_User_99__A-Incomplete_User_99
e 53 54 A-Incomplete_User_99__W-Call-incomplete-files-suspend_User_99
e 54 55 W-Call-incomplete-files-suspend_User_99__W-Call-incomplete-files-resume_User_92
e 55 56 W-Call-incomplete-files-resume_User_92__W-Call-incomplete-files-suspend_User_92
e 56 57 W-Call-incomplete-files-suspend_User_92__W-Call-incomplete-files-ate-abort_User_113
e 57 58 W-Call-incomplete-files-ate-abort_User_113__W-Validate-application-schedule_User_113
e 58 59 W-Validate-application-schedule_User_113__W-Validate-application-start_User_113
e 59 60 W-Validate-application-start_User_113__A-Validating_User_113
e 60 61 A-Validating_User_113__W-Validate-application-suspend_User_113
e 61 62 W-Validate-application-suspend_User_113__W-Validate-application-resume_User_99
e 62 63 W-Validate-application-resume_User_99__W-Validate-application-complete_User_99
e 63 64 W-Validate-application-complete_User_99__W-Call-incomplete-files-schedule_User_99
e 64 65 W-Call-incomplete-files-schedule_User_99__W-Call-incomplete-files-start_User_99
e 65 66 W-Call-incomplete-files-start_User_99__A-Incomplete_User_99
e 66 67 A-Incomplete_User_99__W-Call-incomplete-files-suspend_User_99
e 67 68 W-Call-incomplete-files-suspend_User_99__W-Call-incomplete-files-resume_User_23
e 68 69 W-Call-incomplete-files-resume_User_23__W-Call-incomplete-files-suspend_User_23
e 69 70 W-Call-incomplete-files-suspend_User_23__W-Call-incomplete-files-resume_User_23
e 70 71 W-Call-incomplete-files-resume_User_23__W-Call-incomplete-files-suspend_User_23
e 71 72 W-Call-incomplete-files-suspend_User_23__W-Call-incomplete-files-resume_User_43
e 72 73 W-Call-incomplete-files-resume_User_43__W-Call-incomplete-files-suspend_User_43
e 73 74 W-Call-incomplete-files-suspend_User_43__W-Call-incomplete-files-resume_User_23
e 74 75 W-Call-incomplete-files-resume_User_23__W-Call-incomplete-files-suspend_User_23
e 75 76 W-Call-incomplete-files-suspend_User_23__W-Call-incomplete-files-resume_User_23
e 76 77 W-Call-incomplete-files-resume_User_23__W-Validate-application-schedule_User_23
e 77 78 W-Validate-application-schedule_User_23__W-Validate-application-start_User_23
e 78 79 W-Validate-application-start_User_23__A-Validating_User_23
e 79 80 A-Validating_User_23__W-Validate-application-suspend_User_23
e 80 81 W-Validate-application-suspend_User_23__W-Validate-application-resume_User_99
e 81 82 W-Validate-application-resume_User_99__A-Denied_User_99
e 82 83 A-Denied_User_99__O-Refused_User_99
e 83 84 O-Refused_User_99__W-Validate-application-complete_User_99
e 84 85 W-Validate-application-complete_User_99__end_User_99

XP
v 1 start_User_1
v 2 A-Create-Application_User_1
v 3 A-Submitted_User_1
v 4 W-Handle-leads-schedule_User_1
v 5 W-Handle-leads-start_User_14
v 6 W-Handle-leads-complete_User_14
v 7 W-Complete-application-schedule_User_14
v 8 W-Complete-application-start_User_14
v 9 A-Concept_User_14
v 10 W-Complete-application-suspend_User_14
v 11 A-Accepted_User_15
v 12 O-Create-Offer_User_28
v 13 O-Created_User_28
v 14 O-Sent-mail-and-online_User_28
v 15 W-Complete-application-ate-abort_User_28
v 16 W-Call-after-offers-schedule_User_28
v 17 W-Call-after-offers-start_User_28
v 18 A-Complete_User_28
v 19 W-Call-after-offers-suspend_User_28
v 20 W-Call-after-offers-resume_User_5
v 21 W-Call-after-offers-suspend_User_5
v 22 W-Call-after-offers-ate-abort_User_112
v 23 W-Validate-application-schedule_User_112
v 24 W-Validate-application-start_User_112
v 25 A-Validating_User_112
v 26 O-Returned_User_112
v 27 W-Validate-application-suspend_User_112
v 28 W-Validate-application-resume_User_68
v 29 W-Validate-application-suspend_User_68
v 30 W-Validate-application-resume_User_68
v 31 A-Denied_User_68
v 32 O-Refused_User_68
v 33 W-Validate-application-complete_User_68
v 34 end_User_68
e 5 6 W-Handle-leads-start_User_14__W-Handle-leads-complete_User_14
e 6 7 W-Handle-leads-complete_User_14__W-Complete-application-schedule_User_14
e 6 9 W-Handle-leads-complete_User_14__A-Concept_User_14
e 7 8 W-Complete-application-schedule_User_14__W-Complete-application-start_User_14
e 8 10 W-Complete-application-start_User_14__W-Complete-application-suspend_User_14
e 9 10 A-Concept_User_14__W-Complete-application-suspend_User_14
e 10 11 W-Complete-application-suspend_User_14__A-Accepted_User_15
e 11 12 A-Accepted_User_15__O-Create-Offer_User_28
e 12 13 O-Create-Offer_User_28__O-Created_User_28
e 13 14 O-Created_User_28__O-Sent-mail-and-online_User_28
e 14 15 O-Sent-mail-and-online_User_28__W-Complete-application-ate-abort_User_28
e 15 16 W-Complete-application-ate-abort_User_28__W-Call-after-offers-schedule_User_28
e 16 17 W-Call-after-offers-schedule_User_28__W-Call-after-offers-start_User_28
e 17 18 W-Call-after-offers-start_User_28__A-Complete_User_28
e 18 19 A-Complete_User_28__W-Call-after-offers-suspend_User_28
e 19 20 W-Call-after-offers-suspend_User_28__W-Call-after-offers-resume_User_5
e 20 21 W-Call-after-offers-resume_User_5__W-Call-after-offers-suspend_User_5
e 21 22 W-Call-after-offers-suspend_User_5__W-Call-after-offers-ate-abort_User_112
e 22 23 W-Call-after-offers-ate-abort_User_112__W-Validate-application-schedule_User_112
e 23 24 W-Validate-application-schedule_User_112__W-Validate-application-start_User_112
e 24 25 W-Validate-application-start_User_112__A-Validating_User_112
e 25 26 A-Validating_User_112__O-Returned_User_112
e 25 27 A-Validating_User_112__W-Validate-application-suspend_User_112
e 26 28 O-Returned_User_112__W-Validate-application-resume_User_68
e 27 28 W-Validate-application-suspend_User_112__W-Validate-application-resume_User_68
e 28 29 W-Validate-application-resume_User_68__W-Validate-application-suspend_User_68
e 29 30 W-Validate-application-suspend_User_68__W-Validate-application-resume_User_68
e 30 31 W-Validate-application-resume_User_68__A-Denied_User_68
e 31 32 A-Denied_User_68__O-Refused_User_68
e 32 33 O-Refused_User_68__W-Validate-application-complete_User_68
e 33 34 W-Validate-application-complete_User_68__end_User_68
e 34 1 end_User_68__start_User_1

