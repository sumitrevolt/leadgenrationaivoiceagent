from app.marketing.sequences.modular_kitchen import get_pilot_config, get_sequence

seq = get_sequence('studio')
print(len(seq), 'emails')
cfg = get_pilot_config()
print(cfg['niche'], cfg['daily_volume'])
