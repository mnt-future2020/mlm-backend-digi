"""
Binary Tree Auto-Placement Service
Handles automatic placement of new users in binary tree structure
"""
from typing import Optional, Tuple
from bson import ObjectId
from app.core.database import users_collection, teams_collection


def find_deepest_left_position(sponsor_id: str) -> Optional[str]:
    """
    Find the deepest LEFT-most available position in sponsor's LEFT leg
    
    Algorithm:
    1. Start at sponsor's left child
    2. Always go left first (depth-first, left-most)
    3. If left is filled, check that node's left child
    4. Continue until finding an empty left position
    5. Return the user_id where the new user should be placed
    
    Returns:
        user_id (str): The user ID under whom the new user should be placed on LEFT
        None: If sponsor's direct left is empty (place directly under sponsor)
    """
    # Check if sponsor's direct left child exists
    left_child = teams_collection.find_one({
        "sponsorId": sponsor_id,
        "placement": "LEFT"
    })
    
    # If no left child, new user goes directly under sponsor on LEFT
    if not left_child:
        return None
    
    # Start traversal from sponsor's left child
    current_user_id = left_child["userId"]
    
    # Traverse down the left leg to find deepest left-most available position
    max_depth = 100  # Prevent infinite loops
    for _ in range(max_depth):
        # Check if current user has a left child
        left_child = teams_collection.find_one({
            "sponsorId": current_user_id,
            "placement": "LEFT"
        })
        
        if not left_child:
            # Found empty left position! Place new user here
            return current_user_id
        
        # Move to the left child and continue
        current_user_id = left_child["userId"]
    
    # Fallback (should not reach here in normal scenarios)
    return current_user_id


def find_deepest_right_position(sponsor_id: str) -> Optional[str]:
    """
    Find the deepest RIGHT-most available position in sponsor's RIGHT leg
    
    Algorithm:
    1. Start at sponsor's right child
    2. Always go right first (depth-first, right-most)
    3. If right is filled, check that node's right child
    4. Continue until finding an empty right position
    5. Return the user_id where the new user should be placed
    
    Returns:
        user_id (str): The user ID under whom the new user should be placed on RIGHT
        None: If sponsor's direct right is empty (place directly under sponsor)
    """
    # Check if sponsor's direct right child exists
    right_child = teams_collection.find_one({
        "sponsorId": sponsor_id,
        "placement": "RIGHT"
    })
    
    # If no right child, new user goes directly under sponsor on RIGHT
    if not right_child:
        return None
    
    # Start traversal from sponsor's right child
    current_user_id = right_child["userId"]
    
    # Traverse down the right leg to find deepest right-most available position
    max_depth = 100  # Prevent infinite loops
    for _ in range(max_depth):
        # Check if current user has a right child
        right_child = teams_collection.find_one({
            "sponsorId": current_user_id,
            "placement": "RIGHT"
        })
        
        if not right_child:
            # Found empty right position! Place new user here
            return current_user_id
        
        # Move to the right child and continue
        current_user_id = right_child["userId"]
    
    # Fallback (should not reach here in normal scenarios)
    return current_user_id


def get_auto_placement_position(sponsor_id: str, preferred_placement: str) -> Tuple[str, str]:
    """
    Get the actual placement position for a new user based on preferred placement
    
    Args:
        sponsor_id: The sponsor's user ID (from referral)
        preferred_placement: "LEFT" or "RIGHT" (user's preference)
    
    Returns:
        Tuple[str, str]: (actual_sponsor_id, placement_side)
            - actual_sponsor_id: The user ID under whom the new user will be placed
            - placement_side: "LEFT" or "RIGHT" (the actual placement side)
    
    Example:
        Admin wants to add user to LEFT side
        Admin's left child is Siva, Siva's left child is Gokul
        Gokul's left is empty
        Returns: (gokul_id, "LEFT")
    """
    if preferred_placement == "LEFT":
        # Find deepest left-most position in left leg
        actual_sponsor = find_deepest_left_position(sponsor_id)
        
        if actual_sponsor is None:
            # Direct left is empty, place under original sponsor
            return sponsor_id, "LEFT"
        else:
            # Place under the found position
            return actual_sponsor, "LEFT"
    
    elif preferred_placement == "RIGHT":
        # Find deepest right-most position in right leg
        actual_sponsor = find_deepest_right_position(sponsor_id)
        
        if actual_sponsor is None:
            # Direct right is empty, place under original sponsor
            return sponsor_id, "RIGHT"
        else:
            # Place under the found position
            return actual_sponsor, "RIGHT"
    
    else:
        # Invalid placement, default to LEFT under original sponsor
        return sponsor_id, "LEFT"


def get_placement_info_for_display(sponsor_id: str, preferred_placement: str) -> dict:
    """
    Get human-readable placement information for UI display
    
    Args:
        sponsor_id: The sponsor's user ID
        preferred_placement: "LEFT" or "RIGHT"
    
    Returns:
        dict: {
            "original_sponsor_id": str,
            "original_sponsor_name": str,
            "actual_sponsor_id": str,
            "actual_sponsor_name": str,
            "placement": str,
            "is_direct_placement": bool
        }
    """
    # Get original sponsor info
    original_sponsor = users_collection.find_one({"_id": ObjectId(sponsor_id)})
    if not original_sponsor:
        return None
    
    # Get auto-placement position
    actual_sponsor_id, placement = get_auto_placement_position(sponsor_id, preferred_placement)
    
    # Get actual sponsor info
    actual_sponsor = users_collection.find_one({"_id": ObjectId(actual_sponsor_id)})
    if not actual_sponsor:
        return None
    
    is_direct = (sponsor_id == actual_sponsor_id)
    
    return {
        "original_sponsor_id": sponsor_id,
        "original_sponsor_name": original_sponsor.get("name", "Unknown"),
        "original_sponsor_referral_id": original_sponsor.get("referralId", "Unknown"),
        "actual_sponsor_id": actual_sponsor_id,
        "actual_sponsor_name": actual_sponsor.get("name", "Unknown"),
        "actual_sponsor_referral_id": actual_sponsor.get("referralId", "Unknown"),
        "placement": placement,
        "is_direct_placement": is_direct,
        "message": f"Will be placed under {actual_sponsor.get('name')} on {placement} side"
    }
