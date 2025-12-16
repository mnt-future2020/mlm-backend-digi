@app.get("/api/admin/team/tree/{user_id}")
async def get_admin_team_tree(
    user_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """Get any user's team tree (admin only)"""
    try:
        # Find user by referralId or ObjectId
        try:
            target_user = users_collection.find_one({"_id": ObjectId(user_id)})
        except:
            target_user = users_collection.find_one({"referralId": user_id})
        
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        target_user_id = str(target_user["_id"])
        
        def build_tree(parent_id, depth=0, max_depth=50):
            if depth > max_depth:
                return None
            
            user = users_collection.find_one({"_id": ObjectId(parent_id)})
            if not user:
                return None
            
            # Get children from teams collection
            left_child = teams_collection.find_one({
                "sponsorId": str(user["_id"]),
                "placement": "LEFT"
            })
            right_child = teams_collection.find_one({
                "sponsorId": str(user["_id"]),
                "placement": "RIGHT"
            })
            
            # Get plan name if exists
            plan_name = None
            if user.get("currentPlan"):
                try:
                    plan = plans_collection.find_one({"_id": ObjectId(user["currentPlan"])}, {"_id": 0})
                    if plan:
                        plan_name = plan.get("name")
                except Exception:
                    plan_name = user.get("currentPlan") if isinstance(user.get("currentPlan"), str) and len(user.get("currentPlan")) < 50 else None
            
            node = {
                "id": str(user["_id"]),
                "name": user["name"],
                "referralId": user["referralId"],
                "placement": user.get("placement"),
                "currentPlan": plan_name,
                "isActive": user.get("isActive", False),
                "leftPV": user.get("leftPV", 0),
                "rightPV": user.get("rightPV", 0),
                "totalPV": user.get("totalPV", 0),
                "profilePhoto": user.get("profilePhoto"),
                "left": None,
                "right": None
            }
            
            if left_child:
                node["left"] = build_tree(left_child["userId"], depth + 1, max_depth)
            
            if right_child:
                node["right"] = build_tree(right_child["userId"], depth + 1, max_depth)
            
            return node
        
        tree = build_tree(target_user_id)
        
        return {
            "success": True,
            "data": tree
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

