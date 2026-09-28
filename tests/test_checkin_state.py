import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from unittest.mock import MagicMock, patch

from checkin import format_check_in_notification, generate_balance_hash, get_user_info


def test_balance_hash_changes_when_quota_changes():
	before = {'account_1': {'quota': 100.0, 'used': 20.0}}
	after = {'account_1': {'quota': 125.0, 'used': 20.0}}

	assert generate_balance_hash(before) != generate_balance_hash(after)


def test_balance_hash_changes_when_used_quota_changes():
	before = {'account_1': {'quota': 100.0, 'used': 20.0}}
	after = {'account_1': {'quota': 100.0, 'used': 21.0}}

	assert generate_balance_hash(before) != generate_balance_hash(after)


def test_balance_hash_is_stable_for_equivalent_balances():
	left = {
		'account_2': {'quota': 50.0, 'used': 1.0},
		'account_1': {'quota': 100.0, 'used': 20.0},
	}
	right = {
		'account_1': {'used': 20.0, 'quota': 100.0},
		'account_2': {'used': 1.0, 'quota': 50.0},
	}

	assert generate_balance_hash(left) == generate_balance_hash(right)


def test_format_check_in_notification_normal():
	detail = {
		'name': 'Account 1',
		'success': True,
		'before_quota': 100.0,
		'before_used': 20.0,
		'after_quota': 125.0,
		'after_used': 20.0,
		'check_in_reward': 25.0,
		'usage_increase': 0.0,
		'balance_change': 25.0,
	}
	result = format_check_in_notification(detail)
	assert '[CHECK-IN] Account 1' in result
	assert '余额: $100.00' in result
	assert '余额: $125.00' in result
	assert '签到获得: +$25.00' in result


def test_format_check_in_notification_no_change():
	detail = {
		'name': 'Account 2',
		'success': True,
		'before_quota': 100.0,
		'before_used': 20.0,
		'after_quota': 100.0,
		'after_used': 20.0,
		'check_in_reward': 0.0,
		'usage_increase': 0.0,
		'balance_change': 0.0,
	}
	result = format_check_in_notification(detail)
	assert '[CHECK-IN] Account 2' in result
	assert '今日已签到，无变化' in result


def test_format_check_in_notification_degraded_after_quota_timeout():
	detail = {
		'name': 'oneideals 邮箱 56423',
		'success': True,
		'before_quota': 828.18,
		'before_used': 5712.96,
		'after_quota': None,
		'after_used': None,
		'error': 'Failed to get user info: timed out...',
	}
	result = format_check_in_notification(detail)
	assert '[CHECK-IN] oneideals 邮箱 56423' in result
	assert '签到状态: [SUCCESS] 签到成功' in result
	assert '余额: $828.18' in result
	assert '[WARN] 最新余额查询异常: Failed to get user info: timed out...' in result


def test_format_check_in_notification_degraded_before_quota_missing():
	detail = {
		'name': 'Account 3',
		'success': True,
		'before_quota': None,
		'before_used': None,
		'after_quota': 150.0,
		'after_used': 10.0,
	}
	result = format_check_in_notification(detail)
	assert '[CHECK-IN] Account 3' in result
	assert '当前余额' in result
	assert '余额: $150.00' in result


def test_format_check_in_notification_failed_checkin():
	detail = {
		'name': 'Account Failed',
		'success': False,
		'error': 'HTTP 401 Unauthorized',
	}
	result = format_check_in_notification(detail)
	assert '[CHECK-IN] Account Failed' in result
	assert '状态: [FAIL] 签到失败' in result
	assert '原因: HTTP 401 Unauthorized' in result


def test_get_user_info_success_first_attempt():
	client = MagicMock()
	response = MagicMock()
	response.status_code = 200
	response.json.return_value = {
		'success': True,
		'data': {'quota': 50000000, 'used_quota': 10000000},
	}
	client.get.return_value = response

	info = get_user_info(client, {}, 'https://api.test/self', retries=1, timeout=5.0)
	assert info['success'] is True
	assert info['quota'] == 100.0
	assert info['used_quota'] == 20.0
	assert client.get.call_count == 1


@patch('time.sleep', return_value=None)
def test_get_user_info_retry_success(mock_sleep):
	client = MagicMock()
	fail_resp = MagicMock()
	fail_resp.status_code = 504

	success_resp = MagicMock()
	success_resp.status_code = 200
	success_resp.json.return_value = {
		'success': True,
		'data': {'quota': 25000000, 'used_quota': 5000000},
	}

	client.get.side_effect = [fail_resp, success_resp]

	info = get_user_info(client, {}, 'https://api.test/self', retries=1, timeout=5.0)
	assert info['success'] is True
	assert info['quota'] == 50.0
	assert client.get.call_count == 2
	mock_sleep.assert_called_once_with(1.5)


@patch('time.sleep', return_value=None)
def test_get_user_info_exhaust_retries_failure(mock_sleep):
	client = MagicMock()
	fail_resp = MagicMock()
	fail_resp.status_code = 500

	client.get.return_value = fail_resp

	info = get_user_info(client, {}, 'https://api.test/self', retries=2, timeout=5.0)
	assert info['success'] is False
	assert 'HTTP 500' in info['error']
	assert client.get.call_count == 3
	assert mock_sleep.call_count == 2
