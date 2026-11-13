import streamlit as st
import requests
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from datetime import datetime, timezone

API='https://api.elections.kalshi.com/trade-api/v2'
st.set_page_config(page_title='JARVIS Kalshi 005',page_icon='📡',layout='centered')
st.title('📡 JARVIS Kalshi 005')
st.caption('Read-only research • $50 paper bankroll • No orders, no account keys')
st.metric('Paper bankroll','$50.00')
st.warning('Market quotes are indicative, not verified executable depth. No independent predictive model is connected; every market defaults to PASS.')

@st.cache_data(ttl=30,show_spinner=False)
def load_markets(pages):
    session=requests.Session(); cursor=None; out=[]; seen=set()
    for _ in range(pages):
        params={'status':'open','mve_filter':'exclude','limit':200}
        if cursor:params['cursor']=cursor
        r=session.get(API+'/markets',params=params,timeout=12,headers={'Accept':'application/json'})
        r.raise_for_status(); data=r.json()
        if not isinstance(data.get('markets'),list):raise ValueError('Malformed API response: missing markets list')
        for m in data['markets']:
            t=m.get('ticker')
            if t and t not in seen:seen.add(t);out.append(m)
        next_cursor=data.get('cursor')
        if not next_cursor or next_cursor==cursor:break
        cursor=next_cursor
    return out

def price(m,field):
    try:
        v=Decimal(str(m[field]));return v if Decimal('0')<v<Decimal('1') else None
    except (KeyError,InvalidOperation,TypeError):return None

def fee(p,n):
    return (Decimal('0.07')*n*p*(1-p)).quantize(Decimal('0.01'),rounding=ROUND_CEILING)

pages=st.slider('API pages (200 markets each)',1,10,3)
if st.button('🔄 Scan Kalshi now',type='primary',use_container_width=True):
    load_markets.clear()
try:
    with st.spinner('Fetching public Kalshi markets…'):
        markets=load_markets(pages)
except (requests.RequestException,ValueError) as e:
    st.error(f'Live data unavailable: {str(e)[:240]}')
    st.info('No fallback or fabricated prices. Check the Streamlit app logs and try again.')
    st.stop()

st.success(f'API returned {len(markets)} unique open non-multivariate markets. Scan time: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}')
rows=[]
for m in markets:
    if m.get('status')!='active' and m.get('status')!='open':continue
    a=price(m,'yes_ask_dollars');b=price(m,'yes_bid_dollars')
    if a is None or b is None or b>a:continue
    try:vol=Decimal(str(m.get('volume_fp',m.get('volume',0))))
    except InvalidOperation:continue
    if vol<=0:continue
    n=1
    rows.append({'ticker':m['ticker'],'title':m.get('title',''),'YES ask':float(a),'YES bid':float(b),'spread':float(a-b),'volume':float(vol),'fee_1':float(fee(a,n)),'break_even_1':float(a+fee(a,n)),'market':m})
rows.sort(key=lambda r:(r['spread'],-r['volume']))
st.write(f'**{len(rows)}** markets passed basic quote/volume checks. None passed independent-edge or order-book-depth verification.')
query=st.text_input('Search tickers or market titles')
filtered=[r for r in rows if query.lower() in (r['ticker']+' '+r['title']).lower()][:75]
for r in filtered:
    with st.expander(f"{r['ticker']} · {r['YES ask']:.2f} YES · {r['title'][:65]}"):
        st.write(r['title'])
        st.write(f"YES bid: ${r['YES bid']:.2f} · YES ask: ${r['YES ask']:.2f} · spread: ${r['spread']:.2f}")
        st.write(f"Reported volume: {r['volume']:,.0f} · estimated 1-contract taker fee: ${r['fee_1']:.2f}")
        st.write(f"Approximate YES break-even including entry fee: {r['break_even_1']*100:.1f}%")
        st.caption('PASS — no independent probability estimate; quote freshness and executable depth not independently verified. Market-specific fees may differ.')

st.divider()
st.subheader('What must be added before any signal')
st.write('1. Authenticated read-only order-book access or another verified executable-depth source. 2. Independently sourced, timestamped probability estimates. 3. Category-specific calibration/backtesting. 4. Fee-schedule verification and spread/slippage modeling. 5. Persistent paper ledger and rate-limit monitoring.')
st.caption('Data are fetched only when the app runs. This is not a 24/7 monitor and does not guarantee coverage of all markets. No trade execution code exists.')
