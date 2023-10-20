import xrpl, os
from xrpl import wallet, utils, transaction
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountInfo, AccountTx
from xrpl.models.transactions import Payment
from schemas import RegistrationRequest, TransactionRequest
from utils import format_transactions, get_account_by_phone, save_to_json, load_data_from_json, encode
from dotenv import load_dotenv
from sms import send_sms
from storage import Account, db

load_dotenv()

JSON_RPC_URL = os.environ.get('JSON_RPC_URL')
CLIENT = JsonRpcClient(JSON_RPC_URL)

def register_account(registration_request: RegistrationRequest, account_type:str):
    try:
        new_wallet = wallet.generate_faucet_wallet(CLIENT)
        db.add_basic_account(Account(
            account_name=registration_request.name,
            account_type=account_type,
            pin=registration_request.pin,
            main_wallet=new_wallet,
            phone_number=registration_request.phone_num,
        ))
    except Exception as e:
        return send_sms("Something went wrong, try again later", registration_request.phone_num)
    send_sms(f"Welcome to Ripple Mobile! \nYour {account_type.lower()} account was successfully created for phone number, {registration_request.phone_num}. \nDial *920*106# to start using Ripple Mobile.", registration_request.phone_num)
    

def check_balance(phone_num: str, pin: str):
    user_account = db.get_account(phone_num)
    if not user_account:
        return "User not found."
    
    if user_account.pin != encode(pin):
        return "Incorrect PIN."
    
    try:
        acct_info = AccountInfo(account=user_account.main_wallet.classic_address, ledger_index="validated")
        response = CLIENT.request(acct_info)
        send_sms(f"Current balance is {int(response.result['account_data']['Balance']) / 1_000_000} XRP", phone_num)
        return f"You have {int(response.result['account_data']['Balance']) / 1_000_000} XRP"
    except Exception as e:
        print(e)
        return "Something went wrong, try again later"

def send_xrp(transaction_request: TransactionRequest):
    user_account = db.get_account(transaction_request.sender_phone_num)
    recipient = db.get_account(transaction_request.recipient_phone_num)
    if not user_account:
        return "User not found."
    if user_account.pin != encode(transaction_request.pin):
        return "Incorrect PIN."
    
    sending_wallet = user_account.main_wallet
    receiving_wallat = recipient.main_wallet
    payment = Payment(
        account=sending_wallet.classic_address,
        amount=utils.xrp_to_drops(transaction_request.amount_xrp),
        destination=recipient['wallet_address']
    )
    
    try:
        signed_tx = transaction.autofill_and_sign(payment, CLIENT, sending_wallet)
        transaction.submit_and_wait(signed_tx, CLIENT)
        acct_info = AccountInfo(account=sending_wallet.classic_address, ledger_index="validated")
        recipient_acct_info = AccountInfo(account=receiving_wallat.classic_address, ledger_index="validated")
        sender_response = CLIENT.request(acct_info)
        recipient_response = CLIENT.request(recipient_acct_info)
        sender_updated_balance = int(sender_response.result['account_data']['Balance']) / 1_000_000
        recipient_updated_balance = int(recipient_response.result['account_data']['Balance']) / 1_000_000
        send_sms(f"Transaction successful, you sent {transaction_request.amount_xrp} XRP to {transaction_request.recipient_phone_num}, your Current Balance is {sender_updated_balance} XRP", transaction_request.sender_phone_num)
        send_sms(f"You have received {transaction_request.amount_xrp} XRP from {transaction_request.sender_phone_num}, your Current Balance is {recipient_updated_balance} XRP", transaction_request.recipient_phone_num)
        return True
    except Exception as e:
        print(e)
        return send_sms("Something went wrong, try again later", transaction_request.sender_phone_num)

def get_account_info(phone:str, pin: str):
    user_account = db.get_account(phone)
    if not user_account:
        return "User not found."

    if user_account.pin != encode(pin):
        return "Incorrect PIN."
    
    try:
        if user_account:
            response = CLIENT.request(AccountInfo(
                account=user_account.main_wallet.classic_address,
                ledger_index="validated",
                strict=True,
            ))
            acct_info = response.result['account_data']
            return f"Address: {acct_info.get('Account')} \nBalance: {int(acct_info.get('Balance')) / 1_000_000} XRP \nSequence: {acct_info.get('Sequence')} \nIndex: {acct_info.get('index')}"
        else:
            return "No account found."
    except Exception as e:
        print(e)
        return "Something went wrong, try again later"
    
def get_transaction_history(phone: str, pin: str) -> str:
    user_account = db.get_account(phone)
    
    if not user_account:
        return "User not found."

    if user_account.pin != encode(pin):
        return "Incorrect PIN."
    
    try:
        response = CLIENT.request(AccountTx(account=user_account.main_wallet.classic_address))
        transactions = response.result["transactions"]
        
        formatted_txn_msg = format_transactions(transactions)
        send_sms(f"Transaction History Summary: \n{formatted_txn_msg}", phone)
        return f"Transaction history has been sent to {phone} via SMS"
    except Exception as e:
        print(e)
        return "Something went wrong, try again later"