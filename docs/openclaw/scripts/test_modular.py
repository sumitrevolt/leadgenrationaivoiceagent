from app.marketing.sequences.modular_kitchen import get_sequence, get_pilot_config
seq = get_sequence('studio')
print(len(seq), 'emails')
cfg = get_pilot_config()
print(cfg['niche'], cfg['daily_volume'])