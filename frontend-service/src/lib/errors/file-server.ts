import { t } from '$lib/i18n';

/** What the SMB codes of the worker mean for an administrator, and what to do about them. */
const NT_STATUS_MESSAGES: Array<[RegExp, () => string]> = [
  [/NT_STATUS_(NO_SUCH_FILE|OBJECT_NAME_NOT_FOUND|OBJECT_PATH_NOT_FOUND|NOT_FOUND)/, () => t('The folder does not exist on the file server. Check its path.')],
  [/NT_STATUS_BAD_NETWORK_NAME/, () => t('The share does not exist on the file server. Check its name.')],
  [/NT_STATUS_ACCESS_DENIED/, () => t('The account of the file server does not have the rights on this folder.')],
  [/NT_STATUS_(LOGON_FAILURE|WRONG_PASSWORD|ACCOUNT_LOCKED_OUT|ACCOUNT_DISABLED|PASSWORD_EXPIRED)/, () => t('The file server refuses its account: check its name and password.')],
  [/NT_STATUS_OBJECT_NAME_COLLISION/, () => t('A folder with this name already exists.')],
  [/NT_STATUS_DIRECTORY_NOT_EMPTY/, () => t('The folder is not empty.')],
  [/NT_STATUS_SHARING_VIOLATION/, () => t('A file of this folder is in use. Try again later.')],
  [/NT_STATUS_(HOST_UNREACHABLE|NETWORK_UNREACHABLE|CONNECTION_REFUSED|IO_TIMEOUT|UNSUCCESSFUL|CONNECTION_DISCONNECTED)/, () => t('The file server does not answer. Check that it is started and that its firewall allows it.')]
];

/** A readable sentence instead of a raw NT_STATUS code; any other message is left as it is. */
export function humanizeFileServerMessage(message: string): string;
export function humanizeFileServerMessage(message: string | null | undefined): string | null | undefined;
export function humanizeFileServerMessage(message: string | null | undefined): string | null | undefined {
  if (!message || !message.includes('NT_STATUS_')) return message;
  const known = NT_STATUS_MESSAGES.find(([pattern]) => pattern.test(message));
  return known ? known[1]() : t('The file server refused the operation.');
}
