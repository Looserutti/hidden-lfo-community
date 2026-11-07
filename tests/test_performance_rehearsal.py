from pathlib import Path
import os
import json
import subprocess
import sys
from scripts.check_performance_rehearsal import validate


def settings(root):
    return dict(DISCORD_BOT_TOKEN='synthetic-test-token',DISCORD_CLIENT_ID='201',DISCORD_GUILD_ID='202',
        VERIFIED_ROLE_ID='203',RULES_CHANNEL_ID='204',ADMIN_DISCORD_IDS='205',PERFORMANCE_CHANNEL_ID='206',
        SESSION_SECRET='synthetic-test-session-secret-of-sufficient-length',DATABASE_URL='sqlite:///'+str(root/'test.db'),
        PERFORMANCE_MANAGEMENT_ENABLED='true',EVENT_PUBLISHING_ENABLED='false',MEMBER_EVENT_ANNOUNCEMENTS_ENABLED='false',
        STAFF_REPORTS_ENABLED='false',ONBOARDING_ENABLED='false',PROJECT_ANNOUNCEMENTS_CHANNEL_ID='')


PRODUCTION=dict(DISCORD_BOT_TOKEN='synthetic-production-reference',DISCORD_CLIENT_ID='101',DISCORD_GUILD_ID='102')


def test_preflight_accepts_separate_test_configuration(tmp_path):
    assert validate(settings(tmp_path),PRODUCTION,directory=tmp_path,allowed_database_root=tmp_path)==[]


def test_preflight_rejects_shared_identity_and_database_escape(tmp_path):
    values={**settings(tmp_path),**PRODUCTION,'DATABASE_URL':'sqlite:////var/community.db'}
    issues=validate(values,PRODUCTION,directory=tmp_path,allowed_database_root=tmp_path)
    for key in PRODUCTION: assert any(key in issue and 'differ' in issue for issue in issues)
    assert any('DATABASE_URL' in issue for issue in issues)
    assert 'synthetic-production-reference' not in str(issues)


def test_preflight_rejects_unrelated_jobs_and_missing_reference(tmp_path):
    values={**settings(tmp_path),'ONBOARDING_ENABLED':'true','EVENT_PUBLISHING_ENABLED':'true'}
    issues=validate(values,{},directory=tmp_path,allowed_database_root=tmp_path)
    assert any('ONBOARDING_ENABLED' in issue for issue in issues)
    assert any('EVENT_PUBLISHING_ENABLED' in issue for issue in issues)
    assert any('Production reference' in issue for issue in issues)


def test_synthetic_rehearsal_and_existing_directory_protection(tmp_path):
    root=Path(__file__).resolve().parent.parent
    output=tmp_path/'rehearsal'
    result=subprocess.run([sys.executable,'-m','scripts.rehearse_performances','--output-dir',str(output)],
        cwd=root,env={**os.environ,'DATABASE_URL':'sqlite:////does-not-exist/never-touch.db'},capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    report=json.loads((output/'rehearsal-results.json').read_text())
    assert report['network_requests']==0 and report['production_data_used'] is False
    assert len(report['passed_checks'])==12 and report['final_state']=='ended'
    before=(output/'synthetic-rehearsal.db').read_bytes()
    again=subprocess.run([sys.executable,'-m','scripts.rehearse_performances','--output-dir',str(output)],
        cwd=root,capture_output=True,text=True)
    assert again.returncode != 0
    assert (output/'synthetic-rehearsal.db').read_bytes()==before
