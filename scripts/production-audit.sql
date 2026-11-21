-- India Votes production audit (READ-ONLY)
-- PostgreSQL only. Every statement is SELECT; this script does not modify data.
-- Run: sudo docker compose exec -T postgres psql -U election_user -d election_results -f -

\echo '=== Table row counts ==='
SELECT 'elections' AS table_name, COUNT(*) AS rows FROM elections
UNION ALL SELECT 'historical_assembly_results', COUNT(*) FROM historical_assembly_results
UNION ALL SELECT 'rounds_ac', COUNT(*) FROM rounds_ac
UNION ALL SELECT 'rounds_pc', COUNT(*) FROM rounds_pc
UNION ALL SELECT 'constituency_status', COUNT(*) FROM constituency_status
UNION ALL SELECT 'parties', COUNT(*) FROM parties
UNION ALL SELECT 'states', COUNT(*) FROM states
ORDER BY table_name;

\echo '=== Historical election coverage ==='
SELECT election_id, election_year,
       STRING_AGG(DISTINCT state_code, '/' ORDER BY state_code) AS states,
       COUNT(*) AS candidate_rows,
       COUNT(DISTINCT (state_code, ac_no)) AS constituencies,
       COUNT(DISTINCT state_code) AS state_count
FROM historical_assembly_results
GROUP BY election_id, election_year
ORDER BY election_year DESC, election_id;

\echo '=== Election metadata states that do not match ECI state primary keys (review) ==='
SELECT e.election_id, e.name, code AS metadata_state_code,
       s.state_code_std, s.state_name
FROM elections e
CROSS JOIN LATERAL jsonb_array_elements_text(e.states::jsonb) AS codes(code)
LEFT JOIN states s ON s.state_code = code
WHERE s.state_code IS NULL
ORDER BY e.sort_date DESC, e.election_id, code;

\echo '=== Archive event IDs present in live elections metadata (review) ==='
SELECT e.election_id, e.name, e.states, e.sort_date,
       COUNT(h.*) AS matching_archive_rows
FROM elections e
JOIN historical_assembly_results h ON h.election_id = e.election_id
GROUP BY e.election_id, e.name, e.states, e.sort_date
ORDER BY e.sort_date DESC, e.election_id;

\echo '=== Metadata records with no historical result rows ==='
SELECT e.election_id, e.name, e.states, e.sort_date
FROM elections e
LEFT JOIN historical_assembly_results h ON h.election_id = e.election_id
WHERE h.election_id IS NULL
ORDER BY e.sort_date DESC, e.election_id;

\echo '=== Duplicate natural keys (should return zero rows) ==='
SELECT election_id, state_code, ac_no, candidate, party_name, COUNT(*) AS duplicate_count
FROM historical_assembly_results
GROUP BY election_id, state_code, ac_no, candidate, party_name
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;

\echo '=== Invalid vote values (should return zero rows) ==='
SELECT election_id, state_code, ac_no, candidate, party_name,
       evm_votes, postal_votes, total_votes
FROM historical_assembly_results
WHERE evm_votes < 0 OR postal_votes < 0 OR total_votes < 0
   OR total_votes <> evm_votes + postal_votes
ORDER BY election_year DESC, state_code, ac_no;

\echo '=== Empty candidate or state/election identifiers (should return zero rows) ==='
SELECT election_id, election_year, state_code, ac_no, candidate, party_name
FROM historical_assembly_results
WHERE COALESCE(BTRIM(election_id), '') = ''
   OR COALESCE(BTRIM(state_code), '') = ''
   OR COALESCE(BTRIM(candidate), '') = ''
   OR ac_no <= 0
ORDER BY election_year DESC, state_code, ac_no;

\echo '=== Constituency coverage by historical event ==='
SELECT election_id, election_year, state_code,
       COUNT(DISTINCT ac_no) AS constituencies,
       MIN(ac_no) AS min_ac_no, MAX(ac_no) AS max_ac_no,
       COUNT(*) AS candidate_rows
FROM historical_assembly_results
GROUP BY election_id, election_year, state_code
ORDER BY election_year DESC, state_code;
