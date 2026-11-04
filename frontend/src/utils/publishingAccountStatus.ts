type WebAccountStatus = {
  status: string
  session_saved?: boolean
  login_required?: boolean
  identity_mismatch?: boolean
  publish_ready?: boolean
  message?: string
}

export function publishingAccountStatus(result: WebAccountStatus) {
  // A saved browser profile is not proof that it belongs to the bound account.
  // Support older servers that report the identity conflict only in the message.
  const mismatch = result.identity_mismatch === true ||
    result.message?.includes('当前登录账号与已绑定账号不一致') === true
  const status = mismatch ? 'identity_mismatch'
    : result.status === 'authorized' && result.login_required !== true ? 'authorized'
    : result.status === 'session_saved' && result.login_required !== true ? 'session_saved'
    : result.status === 'login_required' ? 'authorizing' : 'disconnected'
  return {
    status,
    session_saved: status === 'session_saved' || (status === 'authorized' && result.session_saved === true),
    publish_ready: status === 'authorized' || (status === 'session_saved' && result.publish_ready === true),
    status_message: ['identity_mismatch', 'authorizing'].includes(status) ? result.message || '' : '',
  }
}
