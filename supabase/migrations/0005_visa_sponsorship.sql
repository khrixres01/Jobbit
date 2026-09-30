-- Jobs abroad that offer visa sponsorship or relocation are eligible in any work mode (on-site, hybrid, remote).
alter type location_eligibility add value if not exists 'visa_sponsorship';
