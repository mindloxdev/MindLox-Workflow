-- Repair: the job id that lives in the query string
--
-- Generated 2026-09-08 against this workspace. 120 rows.
--
-- WHY
-- `canonical_url` used to drop the whole query string, so on every site that
-- keeps the posting id there -- TeamHealth ?jobid=, ADP ?jobId=, LinkedIn
-- ?currentJobId=, Indeed ?vjk= -- every posting on that site collapsed into one
-- job row. In this database that fused, among others, five TeamHealth postings
-- into job 124, which then carried eight applications from eight profiles that
-- were really eight different jobs.
--
-- The code fix keeps the parameters that name the posting and still drops the
-- tracking ones. This script brings the rows already in the table onto the same
-- identity, so the fixed build matches them instead of creating a second row
-- beside each one and counting the work twice.
--
-- WHY NOT DELETE AND REBUILD
-- 98 of these 120 postings are no longer on any sheet -- older rounds' uploads
-- are gone. Deleting the rows would take 256 applications with them (the FK is
-- ON DELETE CASCADE) and no rebuild could bring them back. This only rewrites
-- the identity; not one application, assignment or interview is touched.
--
-- SAFE TO RUN TWICE. Each row is matched on the fingerprint it has now, so a
-- second run updates nothing.
--
-- ORDER: deploy the code first, then run this. The other way round leaves the
-- old build briefly unable to match its own rows.
--
-- ---------------------------------------------------------------------------
-- 1. Look first. This is what will change.
-- ---------------------------------------------------------------------------
-- SELECT id, title, company, fingerprint, url FROM jobs
--  WHERE fingerprint LIKE 'url:%' AND fingerprint NOT LIKE '%?%'
--    AND url ~* '[?&](jobid|jobno|jobcode|jobseqno|jobopeningid|currentjobid|vjk|jk|gh_jid|opportunityid|postingid|postingseq|requisitionid|reqid|req|vacancyid|positionid|career_job_req_id|indeedapplyablejobid)='
--  ORDER BY id;

BEGIN;

UPDATE jobs AS j
   SET fingerprint = v.new_fp
  FROM (VALUES
    (6, 'url:linkedin.com/jobs/search-results', 'url:linkedin.com/jobs/search-results?currentjobid=4460241537'),   -- Care Navigation and Benefits Specialist @ Jobgether
    (12, 'url:recruiting.ultipro.com/new1028ndbh/jobboard/0ef86aac-4b07-4f64-be80-2cccdb63cf41/opportunitydetail', 'url:recruiting.ultipro.com/new1028ndbh/jobboard/0ef86aac-4b07-4f64-be80-2cccdb63cf41/opportunitydetail?opportunityid=7514b8df-e0ac-43fe-b97a-62e3b861f46f'),   -- Senior Coordinator, Care Access @ Lucet
    (16, 'url:recruiting.ultipro.com/qua1015qdx/jobboard/6c3a5901-71eb-469e-bc54-32e75ea40735/opportunitydetail', 'url:recruiting.ultipro.com/qua1015qdx/jobboard/6c3a5901-71eb-469e-bc54-32e75ea40735/opportunitydetail?opportunityid=c0ebee50-554a-444a-ad05-63c710c5ad39'),   -- Appeals Specialist @ Quadax, Inc.
    (17, 'url:careers.amerihealthcaritas.com/us/en/hvhapply', 'url:careers.amerihealthcaritas.com/us/en/hvhapply?jobseqno=amcaus44648externalenus'),   -- Care Connector @ AmeriHealth Caritas
    (28, 'url:sjobs.brassring.com/tgnewui/search/home/homewithpreload', 'url:sjobs.brassring.com/tgnewui/search/home/homewithpreload?jobid=1839128'),   -- Patient Care Advocate Remote (Texas Only) @ Walgreens
    (35, 'url:linkedin.com/jobs/search', 'url:linkedin.com/jobs/search?currentjobid=4462044096'),   -- Client Experience Specialist @ InfoTrack US
    (49, 'url:deaconess.rec.pro.ukg.net/dea1005deac/jobboard/a1f943e7-8d4d-4348-bf5e-4664f78d3abb/opportunitydetail', 'url:deaconess.rec.pro.ukg.net/dea1005deac/jobboard/a1f943e7-8d4d-4348-bf5e-4664f78d3abb/opportunitydetail?opportunityid=e1c98643-059b-41b2-a093-a32392ddef83'),   -- Patient Account Representative I @ Deaconess Health Syst
    (51, 'url:workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html', 'url:workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html?jobid=1006367'),   -- RCM Specialist II - REMOTE @ Paradigm Oral Health
    (61, 'url:recruiting2.ultipro.com/ten1002thmi/jobboard/617264f5-2868-4e72-899e-78a68c5361f8/opportunitydetail', 'url:recruiting2.ultipro.com/ten1002thmi/jobboard/617264f5-2868-4e72-899e-78a68c5361f8/opportunitydetail?opportunityid=78ac75ae-02db-4f5d-b85c-555aace2de0f'),   -- Medical Billing Specialist - Remote @ American Health Pa
    (78, 'url:recruiting.ultipro.com/int1078ihcs/jobboard/0f2d0fd8-1ec0-46a7-a389-79c391c42aab/opportunitydetail', 'url:recruiting.ultipro.com/int1078ihcs/jobboard/0f2d0fd8-1ec0-46a7-a389-79c391c42aab/opportunitydetail?opportunityid=6aa4584'),   -- RCM Contract Support Specialist @ Integrated Home Care S
    (94, 'url:mypainsolution.rec.pro.ukg.net/cps1500cpsh/jobboard/fd920cb5-f1c6-4ec0-91fa-94fd5b0fe8c6/opportunitydetail', 'url:mypainsolution.rec.pro.ukg.net/cps1500cpsh/jobboard/fd920cb5-f1c6-4ec0-91fa-94fd5b0fe8c6/opportunitydetail?opportunityid=55f17de9-21e1-40b7-abfb-ceffa1e6ca89'),   -- Prior Authorization Specialist @ Commonwealth Pain & Spi
    (110, 'url:careers.rchsd.org/psc/prdexh/employee/hrms/c/hrs_hram_fl.hrs_cg_search_fl.gbl', 'url:careers.rchsd.org/psc/prdexh/employee/hrms/c/hrs_hram_fl.hrs_cg_search_fl.gbl?jobopeningid=19392&postingseq=1'),   -- Patient Access Representative II - Central Scheduling @ 
    (117, 'url:indeed.com/jobs', 'url:indeed.com/jobs?vjk=f5e45c71c6730c57'),   -- Billing Specialist (Remote) @ Pyramid Healthcare
    (124, 'url:teamhealthcareers.com/tgnewui/search/home/homewithpreload', 'url:teamhealthcareers.com/tgnewui/search/home/homewithpreload?jobid=860909'),   -- Overpayment (Refund) Representative @ TeamHealth
    (140, 'url:indeed.com/q-accounts-receivable-specialist-l-remote-jobs.html', 'url:indeed.com/q-accounts-receivable-specialist-l-remote-jobs.html?vjk=1f7d441486694b71'),   -- Accounts Receivable Specialist @ D4C Dental Brands, Inc.
    (144, 'url:myjobs.adp.com/externallincarecareers/cx/job-details', 'url:myjobs.adp.com/externallincarecareers/cx/job-details?reqid=5001222397306'),   -- Customer Service Rep @ Lincare
    (170, 'url:recruiting.ultipro.com/ams1004amsrg/jobboard/501d296e-b63b-46ea-8576-a6cce616dfa5/opportunitydetail', 'url:recruiting.ultipro.com/ams1004amsrg/jobboard/501d296e-b63b-46ea-8576-a6cce616dfa5/opportunitydetail?opportunityid=2e5c12ad-5212-4278-958d-5080662745e2'),   -- Customer Services Representative (Billing) @ AMSURG
    (760, 'url:indeed.com/q-billing-specialist-l-remote-jobs.html', 'url:indeed.com/q-billing-specialist-l-remote-jobs.html?vjk=57ba048f4c05af50'),   -- Insurance Billing Specialist @ The Latchlink
    (770, 'url:apply.deloitte.com/en_us/careers/invitetoapply', 'url:apply.deloitte.com/en_us/careers/invitetoapply?jobid=353751'),   -- Billing and Accounts Receivable Manager @ deloitte
    (779, 'url:indeed.com', 'url:indeed.com?vjk=ad747acc9ee2570a'),   -- Medical Billing Supervisor @ Doctors Pediatric PC
    (806, 'url:assembly.health/careers', 'url:assembly.health/careers?gh_jid=5227966008'),   -- Medical Billing Call Center Representative @ assembly.he
    (809, 'url:indeed.com/q-rcm-remote-jobs.html', 'url:indeed.com/q-rcm-remote-jobs.html?vjk=0657d3d926779ef1'),   -- Medical Billing Coordinator @ LifeStance Health
    (851, 'url:workforcenow.adp.com/mascsr/applicant/mdf/recruitment/postlogin.html', 'url:workforcenow.adp.com/mascsr/applicant/mdf/recruitment/postlogin.html?jobid=545919&jobid=545919&requisitionid=9200903677198_1'),   -- Remote Collection Specialist @ Shreveport
    (893, 'url:genedx.com/careers/openings', 'url:genedx.com/careers/openings?gh_jid=4713612005'),   -- Payment Integrity Specialist @ genedx
    (902, 'url:veracyte.com/company/careers/job-detail', 'url:veracyte.com/company/careers/job-detail?gh_jid=5142910007'),   -- Reimbursement Specialist (PST Time Zone) @ veracyte
    (940, 'url:jagpt.rec.pro.ukg.net/jag1500jago/jobboard/21c4e059-ca21-401a-bf29-82568d4c0389/opportunitydetail', 'url:jagpt.rec.pro.ukg.net/jag1500jago/jobboard/21c4e059-ca21-401a-bf29-82568d4c0389/opportunitydetail?opportunityid=a38a1d39-cbdf-4528-9510-d3e87c36b180'),   -- RCM Specialist- Accounts Receivable & Denial RCS @ JAG P
    (954, 'url:ats.rippling.com/ellit-groups-llc/jobs/683e52a4-9977-40ba-a221-f5dee1fe7cbc/apply', 'url:ats.rippling.com/ellit-groups-llc/jobs/683e52a4-9977-40ba-a221-f5dee1fe7cbc/apply?jobid=683e52a4-9977-40ba-a221-f5dee1fe7cbc'),   -- Staff Accountant @ Ellit Groups
    (971, 'url:recruiting.ultipro.com/sur1003srgi/jobboard/8c80bbae-4c43-4329-a6ad-26bf40795404/opportunitydetail', 'url:recruiting.ultipro.com/sur1003srgi/jobboard/8c80bbae-4c43-4329-a6ad-26bf40795404/opportunitydetail?opportunityid=e812e1b6-770b-4277-99b3-72e9e5f960d7'),   -- Insurance Accounts Receivable Specialist @ Surgical Info
    (972, 'url:servcorphr.hrmdirect.com/employment/job-opening.php', 'url:servcorphr.hrmdirect.com/employment/job-opening.php?req=3700643'),   -- Accounts Receivable Specialist I #Full Time #Remote @ Co
    (1000, 'url:recruiting.ultipro.com/sur1003srgi/jobboard/8c80bbae-4c43-4329-a6ad-26bf40795404/opportunityapply', 'url:recruiting.ultipro.com/sur1003srgi/jobboard/8c80bbae-4c43-4329-a6ad-26bf40795404/opportunityapply?opportunityid=4a4412b4-78e3-4d42-a8ef-bbd4c0fad3c2'),   -- Insurance AR Specialist - Remote @ Surgical Information 
    (1009, 'url:recruiting2.ultipro.com/pre1027prld/jobboard/ae7e164c-0d2a-41b6-8d60-443bc4a9cf8b/opportunitydetail', 'url:recruiting2.ultipro.com/pre1027prld/jobboard/ae7e164c-0d2a-41b6-8d60-443bc4a9cf8b/opportunitydetail?opportunityid=10e2650f-afbd-4194-a792-120a490a33ee'),   -- Medical Billing Specialist - Women''''s Health @ Prelude
    (1014, 'url:recruiting2.ultipro.com/cor1025cvel/jobboard/661856a2-40b3-49f9-ab1e-9845cfac508d/opportunitydetail', 'url:recruiting2.ultipro.com/cor1025cvel/jobboard/661856a2-40b3-49f9-ab1e-9845cfac508d/opportunitydetail?opportunityid=ad3218d0-f40b-4987-8de3-9fbb003a3bf6'),   -- CareIQ Billing Specialist I @ CorVel Corp
    (1022, 'url:bluecloud.rec.pro.ukg.net/blu1503blps/jobboard/acf747ad-6830-44fa-a40c-a52d7d0573f7/opportunitydetail', 'url:bluecloud.rec.pro.ukg.net/blu1503blps/jobboard/acf747ad-6830-44fa-a40c-a52d7d0573f7/opportunitydetail?opportunityid=f84dd75a-3bda-44ac-8104-27c20a1e4337'),   -- Accounts Receivable Representative @ Blue Cloud Pediatri
    (1036, 'url:recruiting2.ultipro.com/get1002gex/jobboard/1c4c6809-36bf-4834-adce-fc1c93fb7f10/opportunitydetail', 'url:recruiting2.ultipro.com/get1002gex/jobboard/1c4c6809-36bf-4834-adce-fc1c93fb7f10/opportunitydetail?opportunityid=985612a0-4b15-4c62-8315-20dfddd16c5f'),   -- Healthcare Customer Service Specialist- (REMOTE) @ Getix
    (1037, 'url:recruiting2.ultipro.com/hus1001husch/jobboard/b6637591-8c8d-49b8-b093-5524b203b157/opportunitydetail', 'url:recruiting2.ultipro.com/hus1001husch/jobboard/b6637591-8c8d-49b8-b093-5524b203b157/opportunitydetail?opportunityid=89ed9345-419c-49c1-8e2c-27c95b0d98b8'),   -- Billing Specialist @ Husch Blackwell
    (1047, 'url:recruiting.ultipro.com/obh1000obhg/jobboard/434f99b5-885e-4000-86de-54a3292c6c1d/opportunitydetail', 'url:recruiting.ultipro.com/obh1000obhg/jobboard/434f99b5-885e-4000-86de-54a3292c6c1d/opportunitydetail?opportunityid=4a5ebbdd-78bd-4273-bfda-473c81cc58f6'),   -- RCM Patient Accounts Receivable Specialist @ Hospitalist
    (1052, 'url:recruiting2.ultipro.com/web1004webin/jobboard/1786dc47-531b-4fc7-a333-399de6a6684c/opportunitydetail', 'url:recruiting2.ultipro.com/web1004webin/jobboard/1786dc47-531b-4fc7-a333-399de6a6684c/opportunitydetail?opportunityid=8706cc30-6733-4788-8add-7db045a4bc67'),   -- Accounts Receivable Specialist II @ WebPT
    (1088, 'url:recruiting.ultipro.com/sgf1000sgfs/jobboard/f17ad3bf-408a-4157-8fb3-305b2cca9616/opportunitydetail', 'url:recruiting.ultipro.com/sgf1000sgfs/jobboard/f17ad3bf-408a-4157-8fb3-305b2cca9616/opportunitydetail?opportunityid=673b878d-5b7a-4624-8c6e-c5d38585236c'),   -- Payment Poster Specialist @ Shady Grove Fertility
    (1152, 'url:eyecare-partners.com/careers-old/current-job-openings', 'url:eyecare-partners.com/careers-old/current-job-openings?gh_jid=8621623002'),   -- RCM OPH/RCM Specialist @ EyeCare Partners
    (1156, 'url:myjobs.adp.com/signatureperformancecareers/cx/job-details', 'url:myjobs.adp.com/signatureperformancecareers/cx/job-details?reqid=5001208928106'),   -- Follow Up Specialist @ Signature Performance, Inc.
    (1208, 'url:divergehealth.org/jobs', 'url:divergehealth.org/jobs?gh_jid=5196980007'),   -- Director of Revenue Cycle @ divergehealth
    (1212, 'url:careers.conduent.com/us/en/apply', 'url:careers.conduent.com/us/en/apply?jobseqno=cojconus24636externalenus'),   -- Medicaid Rebate Analyst Services Specialist @ Conduent
    (1228, 'url:myjobs.adp.com/rayusexternalcareers/cx/job-details', 'url:myjobs.adp.com/rayusexternalcareers/cx/job-details?reqid=5001214852600'),   -- Patient Coordinator @ @ RAYUS Radiology
    (1331, 'url:recruiting.ultipro.com/wel1014wels/jobboard/9af5d0d9-0c68-4e9c-8550-427616af4eaf/opportunitydetail', 'url:recruiting.ultipro.com/wel1014wels/jobboard/9af5d0d9-0c68-4e9c-8550-427616af4eaf/opportunitydetail?opportunityid=87925672-0150-47f1-a4fd-845c39edb6ea'),   -- Payment Poster @ Beaumont Urgent Care
    (1336, 'url:externalcareers-ohsu.icims.com/jobs/login', 'url:externalcareers-ohsu.icims.com/jobs/login?jobid=40740'),   -- Patient Access Resource Specialist @ Oregon Health & Sci
    (1383, 'url:birdiinc.rec.pro.ukg.net/bir1501biin/jobboard/b8a98ec2-8b9c-4847-bc79-3f04b752a753/opportunitydetail', 'url:birdiinc.rec.pro.ukg.net/bir1501biin/jobboard/b8a98ec2-8b9c-4847-bc79-3f04b752a753/opportunitydetail?opportunityid=1d31c916-9f4e-46b3-85b2-774c7a1a70eb'),   -- Lead Patient Care Coordinator @ @ Birdi
    (1409, 'url:cchsconnect.rec.pro.ukg.net/col1053cchd/jobboard/c6df4630-7da9-4627-af22-819e939d86fa/opportunityapply', 'url:cchsconnect.rec.pro.ukg.net/col1053cchd/jobboard/c6df4630-7da9-4627-af22-819e939d86fa/opportunityapply?opportunityid=bc4f15d4-1555-4e42-bc00-785ddd0a7340&postingid=b2c0dd71-96f2-4926-817f-18f745f9cbab'),   -- Revenue Cycle Specialist II - Biller (Remote in WA, ID, 
    (1428, 'url:wellthy.com/careers/post', 'url:wellthy.com/careers/post?gh_jid=7895392003'),   -- Care Coordinator @ Wellthy
    (1431, 'url:recruiting2.ultipro.com/sig1008sigh/jobboard/cf92642a-98a5-4c01-b0b8-f7305a74d51c/opportunitydetail', 'url:recruiting2.ultipro.com/sig1008sigh/jobboard/cf92642a-98a5-4c01-b0b8-f7305a74d51c/opportunitydetail?opportunityid=7911042b-d551-4952-8d01-bdcb281c6836'),   -- Customer Reimbursement Coordinator @ Sight Sciences
    (1475, 'url:recruiting.ultipro.com/uni1043upinc/jobboard/ceba5eaa-bf0a-4e03-b4aa-6bf1be2c413d/opportunitydetail', 'url:recruiting.ultipro.com/uni1043upinc/jobboard/ceba5eaa-bf0a-4e03-b4aa-6bf1be2c413d/opportunitydetail?opportunityid=549835f1-576d-48ff-bf9a-99a22bf8860c&postingid=78135e14-0f97-4f66-8d58-8230ba382360'),   -- Lead Accounts Receivable Claims Specialist (Chesapeake S
    (1498, 'url:kuresmart.hrmdirect.com/employment/job-opening.php', 'url:kuresmart.hrmdirect.com/employment/job-opening.php?req=3793123'),   -- Billing Specialist I @ Clearway Pain Solutions
    (1517, 'url:recruiting2.ultipro.com/med1007mhp/jobboard/ffa5492f-9175-4dab-891d-a6a5d6dced2f/opportunitydetail', 'url:recruiting2.ultipro.com/med1007mhp/jobboard/ffa5492f-9175-4dab-891d-a6a5d6dced2f/opportunitydetail?opportunityid=d1cb3ef6-d4c2-4275-9fd5-dab468620c07'),   -- UM Review Coordinator II @ Medica
    (1528, 'url:recruiting.ultipro.com/ame1070/jobboard/cbf863ee-da68-4d60-9da0-e17b3404411c/opportunityapply', 'url:recruiting.ultipro.com/ame1070/jobboard/cbf863ee-da68-4d60-9da0-e17b3404411c/opportunityapply?opportunityid=00057947-748d-4c87-8e96-e84c02c46b8f'),   -- Clinical Operations Coordinator - Illinois Market @ Rasm
    (1535, 'url:recruiting.ultipro.com/sur1004srgy/jobboard/aa616d8f-f2a8-46c2-8f8e-1ca56e162ffd/opportunitydetail', 'url:recruiting.ultipro.com/sur1004srgy/jobboard/aa616d8f-f2a8-46c2-8f8e-1ca56e162ffd/opportunitydetail?opportunityid=dd8d8528-141e-461a-97f0-9f668abfa52a'),   -- Biller - Remote @ @ Surgery Partners
    (1552, 'url:charliehealth.com/careers', 'url:charliehealth.com/careers?gh_jid=5777935004'),   -- Care Admin Specialist (Full Time) @ Charlie Health
    (1554, 'url:jobs.bswhealth.com/us/en/apply', 'url:jobs.bswhealth.com/us/en/apply?jobseqno=bswhus26012379externalenus'),   -- Access Services Rep 1 @ Baylor Scott & White Health
    (1593, 'url:recruitment.connextglobal.com/intake-form', 'url:recruitment.connextglobal.com/intake-form?jobid=3101'),   -- Patient Care Coordinator @ Connext
    (1619, 'url:toalliance.rec.pro.ukg.net/ten1507teoa/jobboard/2dd4fa7b-f400-4d4f-8199-749fd019b8e9/opportunitydetail', 'url:toalliance.rec.pro.ukg.net/ten1507teoa/jobboard/2dd4fa7b-f400-4d4f-8199-749fd019b8e9/opportunitydetail?opportunityid=8f6160f0-9db2-41d3-9142-424fd7ae793e'),   -- AR Specialist @ Tennessee Orthopaedic Alliance
    (1798, 'url:smartapply.indeed.com/beta/indeedapply/applybyapplyablejobid', 'url:smartapply.indeed.com/beta/indeedapply/applybyapplyablejobid?indeedapplyablejobid=880f8593-2b14-4ddd-8127-6043680c98e7-exvschjvzde'),   -- Director of Revenue Cycle @ INFUSION SOLUTIONS INC
    (1958, 'url:bluecloud.rec.pro.ukg.net/blu1503blps/jobboard/acf747ad-6830-44fa-a40c-a52d7d0573f7/opportunityapply', 'url:bluecloud.rec.pro.ukg.net/blu1503blps/jobboard/acf747ad-6830-44fa-a40c-a52d7d0573f7/opportunityapply?opportunityid=a09ceaac-eb0e-487f-ade8-456c3166aac3'),   -- Accounts Receivable Representative @ Blue Cloud Pediatri
    (1990, 'url:recruiting.ultipro.com/qua1015qdx/jobboard/6c3a5901-71eb-469e-bc54-32e75ea40735/opportunityapply', 'url:recruiting.ultipro.com/qua1015qdx/jobboard/6c3a5901-71eb-469e-bc54-32e75ea40735/opportunityapply?opportunityid=e1c1b83f-6e68-40da-9bb2-2f9346fb9371'),   -- Insurance Specialist @ Quadax, Inc.
    (1993, 'url:myjobs.adp.com/claritevcareers/cx/job-details', 'url:myjobs.adp.com/claritevcareers/cx/job-details?reqid=5001207374706'),   -- Claims Resolution Specialist @ Claritev
    (2266, 'url:myjobs.adp.com/signatureperformancecareers/cx/app', 'url:myjobs.adp.com/signatureperformancecareers/cx/app?reqid=5001212544906'),   -- Follow Up Specialist III @ Signature Performance, Inc
    (2298, 'url:myjobs.adp.com/joinaegvision/cx/app', 'url:myjobs.adp.com/joinaegvision/cx/app?reqid=5001209177306'),   -- Patient Care Coordinator @ AEG Vision
    (2327, 'url:ats.rippling.com/first-gen-careers/jobs/c2d6487c-abda-4934-85b0-544a3520bf2b/apply', 'url:ats.rippling.com/first-gen-careers/jobs/c2d6487c-abda-4934-85b0-544a3520bf2b/apply?jobid=c2d6487c-abda-4934-85b0-544a3520bf2b'),   -- Billing Specialist @ First Gen Financial
    (2353, 'url:myjobs.adp.com/edenhealthexternalcs/cx/app', 'url:myjobs.adp.com/edenhealthexternalcs/cx/app?reqid=5001212533706'),   -- Billing Specialist @ Eden Health
    (2374, 'url:myjobs.adp.com/revecorecareers/cx/job-details', 'url:myjobs.adp.com/revecorecareers/cx/job-details?reqid=5001215043806'),   -- Health Eligibility Claims Specialist - Part Time @ Revec
    (2484, 'url:datavant.com/about/careers/open-roles/job', 'url:datavant.com/about/careers/open-roles/job?gh_jid=5383141008'),   -- Health Information Specialist I @ Datavant
    (2494, 'url:recruiting2.ultipro.com/cor1025cvel/jobboard/661856a2-40b3-49f9-ab1e-9845cfac508d/opportunityapply', 'url:recruiting2.ultipro.com/cor1025cvel/jobboard/661856a2-40b3-49f9-ab1e-9845cfac508d/opportunityapply?opportunityid=ff21fb54-d17d-4d5b-84bf-90fdc92622ee'),   -- Revenue Cycle Specialist I @ CorVel Corp
    (2549, 'url:recruiting.ultipro.com/uni1043upinc/jobboard/ceba5eaa-bf0a-4e03-b4aa-6bf1be2c413d/opportunityapply', 'url:recruiting.ultipro.com/uni1043upinc/jobboard/ceba5eaa-bf0a-4e03-b4aa-6bf1be2c413d/opportunityapply?opportunityid=549835f1-576d-48ff-bf9a-99a22bf8860c&postingid=78135e14-0f97-4f66-8d58-8230ba382360'),   -- Lead Accounts Receivable Claims Specialist (Chesapeake S
    (2582, 'url:careers.bsmhealth.org/us/en/apply', 'url:careers.bsmhealth.org/us/en/apply?jobseqno=bsmbsmusr284024externalenus'),   -- Accounts Receivable Specialist - Work at Home - Ohio - P
    (2628, 'url:career41.sapsf.com/portalcareer', 'url:career41.sapsf.com/portalcareer?career_job_req_id=36692'),   -- Healthcare Customer Service Representative - Remote KS @
    (2644, 'url:ats.rippling.com/nocd/jobs/d7f95526-f40a-4bd0-b355-5e7309d8bf8e/apply', 'url:ats.rippling.com/nocd/jobs/d7f95526-f40a-4bd0-b355-5e7309d8bf8e/apply?jobid=d7f95526-f40a-4bd0-b355-5e7309d8bf8e'),   -- Revenue Cycle Specialist @ NOCD
    (2655, 'url:careers.ecuhealth.org/us/en/apply', 'url:careers.ecuhealth.org/us/en/apply?jobseqno=ebsehsus983837externalenus'),   -- Manager, Denial Management @ ECU Health
    (2701, 'url:careers.mwhs1.com/us/en/apply', 'url:careers.mwhs1.com/us/en/apply?jobseqno=mosmhsusjreq015059externalenus'),   -- Medical Accounts Receivable Specialist - Remote @ Moses 
    (2723, 'url:careers.dukehealth.org/us/en/apply', 'url:careers.dukehealth.org/us/en/apply?jobseqno=duhduhus274038externalenus'),   -- Patient Service Representative - Outpatient Eligibility/
    (2745, 'url:radpartners.avature.net/careers/applicationmethods', 'url:radpartners.avature.net/careers/applicationmethods?jobid=19901'),   -- Patient Account Rep I @ Radiology Partners
    (2750, 'url:recruiting.ultipro.com/ams1004amsrg/jobboard/94a3d750-7693-4943-8b5d-0a9b17bb4e4f/opportunitydetail', 'url:recruiting.ultipro.com/ams1004amsrg/jobboard/94a3d750-7693-4943-8b5d-0a9b17bb4e4f/opportunitydetail?opportunityid=a9a195ca-7593-4920-a91b-66e89da67537'),   -- Customer Services Representative (Verification of Benefi
    (2888, 'url:indeed.com/q-medical-billing-l-remote-jobs.html', 'url:indeed.com/q-medical-billing-l-remote-jobs.html?vjk=9df939977a1d1946'),   -- Insurance AR Specialist @ CBS Medical Billing & Consulti
    (2894, 'url:indeed.com/q-medical-receptionist-l-remote-jobs.html', 'url:indeed.com/q-medical-receptionist-l-remote-jobs.html?vjk=32e9f0c9e4eb47f3'),   -- Patient Access Specialist @ access healthcare service
    (2901, 'url:indeed.com/q-remote-patient-scheduler-l-remote-jobs.html', 'url:indeed.com/q-remote-patient-scheduler-l-remote-jobs.html?vjk=c72c7880a89b65c6'),   -- ABA Therapy Scheduler (Remote Position) @ House of Heart
    (3038, 'url:indeed.com/q-patient-care-coordinator-l-remote-jobs.html', 'url:indeed.com/q-patient-care-coordinator-l-remote-jobs.html?vjk=306bf9c80d75480c'),   -- Patient Care Coordinator @ Laguna Beach Community Clinic
    (3052, 'url:ats.rippling.com/directmeds/jobs/33e68ddc-9c1e-4ace-8be5-60a2019f9234/apply', 'url:ats.rippling.com/directmeds/jobs/33e68ddc-9c1e-4ace-8be5-60a2019f9234/apply?jobid=33e68ddc-9c1e-4ace-8be5-60a2019f9234'),   -- Customer Service Representative – Remote @ @ Direct Meds
    (3058, 'url:ats.rippling.com/1nhealth/jobs/44a655db-43a2-4764-9cc9-a2c64d880a10/apply', 'url:ats.rippling.com/1nhealth/jobs/44a655db-43a2-4764-9cc9-a2c64d880a10/apply?jobid=44a655db-43a2-4764-9cc9-a2c64d880a10'),   -- Patient Coordinator Support Lead @ @ 1nHealth
    (3107, 'url:indeed.com/q-revenue-cycle-management-l-remote-jobs.html', 'url:indeed.com/q-revenue-cycle-management-l-remote-jobs.html?vjk=8f5ab6ed61ad4cdc'),   -- Denials Specialist (Revenue Cycle Management) @ Healthca
    (3118, 'url:indeed.com/q-ar-specialist-l-remote-jobs.html', 'url:indeed.com/q-ar-specialist-l-remote-jobs.html?vjk=5cbb3b4f55a1d9fe'),   -- AR Follow-Up Representative @ Integra Connect
    (3120, 'url:indeed.com/q-work-from-home-customer-service-l-remote-jobs.html', 'url:indeed.com/q-work-from-home-customer-service-l-remote-jobs.html?vjk=1fc472da6a8e832a'),   -- Customer Service Representative (Seasonal - Remote) @ WT
    (3129, 'url:indeed.com/q-part-time-customer-service-l-remote-jobs.html', 'url:indeed.com/q-part-time-customer-service-l-remote-jobs.html?vjk=f42231f168752203'),   -- Part Time Temp Customer Service Representative @ Automat
    (3197, 'url:indeed.com/q-medical-billing-specialist-l-remote-jobs.html', 'url:indeed.com/q-medical-billing-specialist-l-remote-jobs.html?vjk=99126a54793cf77c'),   -- Medical Billing Specialist @ Ultimate Medical Billing an
    (3202, 'url:indeed.com/q-remote-denials-management-specialist-l-remote-jobs.html', 'url:indeed.com/q-remote-denials-management-specialist-l-remote-jobs.html?vjk=6de71efe851add8c'),   -- Supervisor, Denials - Resolution Management @ Aspirion
    (3204, 'url:indeed.com/q-customer-service-representative-l-remote-jobs.html', 'url:indeed.com/q-customer-service-representative-l-remote-jobs.html?vjk=7aef1fce87c92d1e'),   -- Remote Call Center Representative - Puerto Rico @ Condue
    (3288, 'url:jobs.silkroad.com/numotion/careers/apply/success', 'url:jobs.silkroad.com/numotion/careers/apply/success?jobid=15584'),   -- Reimbursement Specialist @ Numotion
    (3334, 'url:ndeed.com/jobs', 'url:ndeed.com/jobs?vjk=46974f3015576d79'),   -- Experienced Medical Billing Specialist - Tebra Experienc
    (3427, 'url:linkedin.com/jobs/collections/recommended', 'url:linkedin.com/jobs/collections/recommended?currentjobid=4420159221'),   -- Billing Specialist @ Optimum Healthcare IT
    (3487, 'url:jobs.trinity-health.org/apply', 'url:jobs.trinity-health.org/apply?jobseqno=trheus00664430externalenus'),   -- REMOTE Scheduling Specialist I @ Trinity Health
    (3570, 'url:myjobs.adp.com/merakeycareers/cx/job-details', 'url:myjobs.adp.com/merakeycareers/cx/job-details?reqid=5001207024706'),   -- Accounts Receivable Coordinator @ Merakey
    (3651, 'url:floridaortho.rec.pro.ukg.net/flo1502fopi/jobboard/638273c0-e381-4548-bc5a-3b676e09e8bf/opportunitydetail', 'url:floridaortho.rec.pro.ukg.net/flo1502fopi/jobboard/638273c0-e381-4548-bc5a-3b676e09e8bf/opportunitydetail?opportunityid=a0194be3-fb4e-4566-8ecb-ad44d6ed67db'),   -- Financial Counselor @ Florida Orthopaedic Institute
    (3771, 'url:recruiting.ultipro.com/twi1001twico/jobboard/9357342e-34af-4051-9753-58a7db39a88e/opportunitydetail', 'url:recruiting.ultipro.com/twi1001twico/jobboard/9357342e-34af-4051-9753-58a7db39a88e/opportunitydetail?opportunityid=c3a19b65-3f31-4dd0-a11a-7c3da992e479'),   -- ASC Billing & Denial Specialist - Revo Health @ Revo Hea
    (3803, 'url:recruiting.ultipro.com/sym1000/jobboard/95b2381b-66d2-45ce-b4ee-1e0f131d98a5/opportunitydetail', 'url:recruiting.ultipro.com/sym1000/jobboard/95b2381b-66d2-45ce-b4ee-1e0f131d98a5/opportunitydetail?opportunityid=9e3796c5-c02e-48e1-9363-eedaa2f06543'),   -- Billing Representative @ TridentCare
    (3826, 'url:recruiting.ultipro.com/awa1000awar/jobboard/e0a2029d-cfad-473e-a0c3-1b969fd0595f/opportunitydetail', 'url:recruiting.ultipro.com/awa1000awar/jobboard/e0a2029d-cfad-473e-a0c3-1b969fd0595f/opportunitydetail?opportunityid=b6eab873-b75e-425c-83fb-cea11cf5be49'),   -- Alumni Coordinator @ Aware Recovery Care
    (3828, 'url:recruiting.ultipro.com/cor1016corei/jobboard/d1445d2b-c378-4a1e-9e18-d5d1a7565517/opportunitydetail', 'url:recruiting.ultipro.com/cor1016corei/jobboard/d1445d2b-c378-4a1e-9e18-d5d1a7565517/opportunitydetail?opportunityid=2c6893e2-80ab-4346-a929-215b4476c584'),   -- Medical Office Scheduler (MRI) @ HOPCo
    (3880, 'url:recruiting2.ultipro.com/nor1027nminc/jobboard/fc008c11-8b24-4834-af91-b281183a52a6/opportunitydetail', 'url:recruiting2.ultipro.com/nor1027nminc/jobboard/fc008c11-8b24-4834-af91-b281183a52a6/opportunitydetail?opportunityid=a548a380-1af2-428f-a138-166b921f122f&postingid=d281e692-a20b-40f2-901d-f43914487bfd'),   -- Customer Service Rep I @ Noridian Healthcare Solutions
    (3889, 'url:recruiting.ultipro.com/mid1031mide/jobboard/34f4f5d3-56e2-4a94-aff4-1940b62a60db/opportunitydetail', 'url:recruiting.ultipro.com/mid1031mide/jobboard/34f4f5d3-56e2-4a94-aff4-1940b62a60db/opportunitydetail?opportunityid=c8c49ae5-ccee-4e70-a05c-6bbca91c0b63'),   -- Revenue Cycle Specialist @ Bridgeview Eye Partners
    (3908, 'url:unmmg.hrmdirect.com/employment/job-opening.php', 'url:unmmg.hrmdirect.com/employment/job-opening.php?req=3746431'),   -- Accounts Receivable Tech II - Must have a NM Residence @
    (3976, 'url:recruiting.ultipro.com/tid1000/jobboard/aee20ff8-316e-4349-b3a3-14132b6404e5/opportunitydetail', 'url:recruiting.ultipro.com/tid1000/jobboard/aee20ff8-316e-4349-b3a3-14132b6404e5/opportunitydetail?opportunityid=27928c09-244d-4877-8ea4-780460633e0d'),   -- Reimbursement Specialist @ Empath Health
    (4025, 'url:jobs.thecignagroup.com/us/en/apply', 'url:jobs.thecignagroup.com/us/en/apply?jobseqno=cignus26009836externalenus'),   -- Revenue Account Specialist - Cigna Healthcare - Remote @
    (4036, 'url:toalliance.rec.pro.ukg.net/ten1507teoa/jobboard/18af4e38-ae8e-4c28-a896-3771d12c32a1/opportunitydetail', 'url:toalliance.rec.pro.ukg.net/ten1507teoa/jobboard/18af4e38-ae8e-4c28-a896-3771d12c32a1/opportunitydetail?opportunityid=8f6160f0-9db2-41d3-9142-424fd7ae793e'),   -- AR Specialist @ Tennessee Orthopaedic Alliance
    (4056, 'url:recruiting2.ultipro.com/ene1003eneng/jobboard/020a913b-6f29-4cb0-a3b2-8b9d82d26c72/opportunitydetail', 'url:recruiting2.ultipro.com/ene1003eneng/jobboard/020a913b-6f29-4cb0-a3b2-8b9d82d26c72/opportunitydetail?opportunityid=5fd20b1d-29df-48a7-b6c7-1c47e683c9f0'),   -- Billing Specialist I @ ENTRUST Solutions Group
    (4096, 'url:jobs.thecignagroup.com/us/en/applythankyou', 'url:jobs.thecignagroup.com/us/en/applythankyou?jobid=26005927&jobseqno=cignus26005927externalenus'),   -- Collections Specialist @ The Cigna Group -
    (4108, 'url:recruiting.ultipro.com/ams1004amsrg/jobboard/94a3d750-7693-4943-8b5d-0a9b17bb4e4f/opportunityapply', 'url:recruiting.ultipro.com/ams1004amsrg/jobboard/94a3d750-7693-4943-8b5d-0a9b17bb4e4f/opportunityapply?opportunityid=e0760958-3222-48c3-9625-eaba8676d2d2'),   -- SUPERVISOR REVENUE CYCLE @ AMSURG
    (4155, 'url:monster.com/apply/start', 'url:monster.com/apply/start?jobid=bb56a17c-9ba4-40fa-beba-deceabe3e870'),   -- Hospital Medicare Biller @ TIS International (USA) Inc
    (4158, 'url:coastalhorizons.hrmdirect.com/employment/view.php', 'url:coastalhorizons.hrmdirect.com/employment/view.php?req=3739988'),   -- Revenue Cycle Specialist, Primary Care @ Coastal Horizon
    (4336, 'url:recruiting.ultipro.com/hol1012hlcb/jobboard/fff42a0c-0ef6-4123-a7c0-742b0c288290/opportunitydetail', 'url:recruiting.ultipro.com/hol1012hlcb/jobboard/fff42a0c-0ef6-4123-a7c0-742b0c288290/opportunitydetail?opportunityid=87f194d1-9e71-40b5-b147-7e1a0e2a033a'),   -- Remote Healthcare Customer Service (Insurance Knowledge 
    (4361, 'url:casadelafamilia.hrmdirect.com/employment/job-opening.php', 'url:casadelafamilia.hrmdirect.com/employment/job-opening.php?req=3786370'),   -- Care Coordination Specialist [Remote @ Casa de la Famili
    (4388, 'url:floridaortho.rec.pro.ukg.net/flo1502fopi/jobboard/1ea52a4f-2ec6-44f6-8005-fec82adb4d30/opportunitydetail', 'url:floridaortho.rec.pro.ukg.net/flo1502fopi/jobboard/1ea52a4f-2ec6-44f6-8005-fec82adb4d30/opportunitydetail?opportunityid=50455bc2-25fe-4ee8-a862-ae7771c16d1c'),   -- Patient Access Representative I -Remote @ Orthopaedic So
    (4397, 'url:bicyclehealth.com/careers-opportunities', 'url:bicyclehealth.com/careers-opportunities?gh_jid=6138797004'),   -- Clinical Support Specialist- West @ Bicycle Health
    (4448, 'url:patientsfirst.rec.pro.ukg.net/pin1501pinf/jobboard/1e044be6-1c30-4d58-8bb6-bbe2a24774ce/opportunitydetail', 'url:patientsfirst.rec.pro.ukg.net/pin1501pinf/jobboard/1e044be6-1c30-4d58-8bb6-bbe2a24774ce/opportunitydetail?opportunityid=73cdb15c-284e-4283-b18b-c90eb9d0e0a0'),   -- Financial Counselor @ Florida Orthopaedic Institute·
    (4552, 'url:freedomcare.com/jobs', 'url:freedomcare.com/jobs?gh_jid=7983833003'),   -- Intake Specialist I (IN / Remote) @ FreedomCare
    (4566, 'url:indeed.com/cmp/bluefish-medical/jobs', 'url:indeed.com/cmp/bluefish-medical/jobs?jk=d558ea7'),   -- Medical Billing Specialist @ Bluefish Medical
    (4580, 'url:recruiting2.ultipro.com/qhc1000qhcs/jobboard/c040c0a4-ac04-44d9-b2db-247ae83b77f4/opportunitydetail', 'url:recruiting2.ultipro.com/qhc1000qhcs/jobboard/c040c0a4-ac04-44d9-b2db-247ae83b77f4/opportunitydetail?opportunityid=636b6524-dc9f-48d9-96bd-08d84c48d273')   -- Revenue Cycle Associate - Collections @ Quorum Health
  ) AS v(id, old_fp, new_fp)
 WHERE j.id = v.id
   AND j.fingerprint = v.old_fp;

-- ---------------------------------------------------------------------------
-- 2. Check before you commit. Expect: updated = 120, still_old = 0, dupes = 0.
-- ---------------------------------------------------------------------------
SELECT count(*) FILTER (WHERE fingerprint LIKE 'url:%?%')        AS updated,
       count(*) FILTER (WHERE fingerprint NOT LIKE 'url:%?%')    AS still_old
  FROM jobs
 WHERE id IN (6, 12, 16, 17, 28, 35, 49, 51, 61, 78, 94, 110, 117, 124, 140, 144, 170, 760, 770, 779, 806, 809, 851, 893, 902, 940, 954, 971, 972, 1000, 1009, 1014, 1022, 1036, 1037, 1047, 1052, 1088, 1152, 1156, 1208, 1212, 1228, 1331, 1336, 1383, 1409, 1428, 1431, 1475, 1498, 1517, 1528, 1535, 1552, 1554, 1593, 1619, 1798, 1958, 1990, 1993, 2266, 2298, 2327, 2353, 2374, 2484, 2494, 2549, 2582, 2628, 2644, 2655, 2701, 2723, 2745, 2750, 2888, 2894, 2901, 3038, 3052, 3058, 3107, 3118, 3120, 3129, 3197, 3202, 3204, 3288, 3334, 3427, 3487, 3570, 3651, 3771, 3803, 3826, 3828, 3880, 3889, 3908, 3976, 4025, 4036, 4056, 4096, 4108, 4155, 4158, 4336, 4361, 4388, 4397, 4448, 4552, 4566, 4580);

SELECT fingerprint, count(*) AS dupes
  FROM jobs GROUP BY fingerprint HAVING count(*) > 1;

-- ---------------------------------------------------------------------------
-- 3. If those read right:
-- ---------------------------------------------------------------------------
-- COMMIT;
-- ...or, if they do not:
-- ROLLBACK;
