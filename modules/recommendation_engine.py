def make_recommendation(tfs, threshold=0.65, min_minutes=3, max_minutes=20, pred_minutes=None):
    t1 = tfs.get('1m', {}); t5 = tfs.get('5m', {}); t10 = tfs.get('10m', {})
    conf5 = t5.get('conf', 0.0); conf10 = t10.get('conf', 0.0)
    dir5 = t5.get('dir', 0); dir10 = t10.get('dir', 0)
    avg_conf = (conf5 + conf10)/2.0
    tf_choice = "5m"; action="انتظار"
    if dir10==1 and dir5==1 and avg_conf>=threshold: action="شراء"
    elif dir10==0 and dir5==0 and avg_conf>=threshold: action="بيع"
    else:
        if t1.get('conf',0)>=threshold and t1.get('dir',0) in (0,1):
            action = "شراء" if t1['dir']==1 else "بيع"; tf_choice="1m"
    if pred_minutes is not None:
        duration = int(max(min_minutes, min(max_minutes, pred_minutes)))
        conf_pct = round(avg_conf*100.0,1)
    else:
        tp_pct = t5.get('tp_pct',0.3) or 0.3
        duration = int(max(min_minutes, min(max_minutes, tp_pct*20)))
        conf_pct = round(avg_conf*100.0,1)
    return {"action": action, "timeframe": tf_choice, "confidence_pct": conf_pct, "duration_min": duration}
