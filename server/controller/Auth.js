const User = require("../models/User");
const OTP = require("../models/otp");
const otpGenerator = require('otp-generator');
const bcrypt = require("bcrypt");
const jwt = require("jsonwebtoken");
require("dotenv").config();
const mailSender = require("../utils/mailSender")
const passwordUpdated = require("../mail/templates/passwordUpdate");
const Profile = require("../models/Profile");
//SendOTP
//signUp kara user ne data insert kiya fir create account par click kiya
exports.sendOtp = async (req,res) =>{
    try{
        //fetch data from req body
        const {email} = req.body;
        //if user already exist to res send karo kuch
        const userPresent = await User.findOne({email});
        if(userPresent){
            return res.status(401).json({
                success:false,
                message:"User already exist so not able to signIn"
            });
        }
        //if user does not exist to  
        //(1)unique otp generate karo
        let otp = otpGenerator.generate(6,{
            specialChars:false,
            upperCaseAlphabets:false,
            lowerCaseAlphabets:false
        });
        let otpInDB = await OTP.findOne({otp});
        while(otpInDB){
            otp = otpGenerator.generate(6,{
                specialChars:false,
                upperCaseAlphabets:false,
                lowerCaseAlphabets:false
            });
            otpInDB = await OTP.findOne({otp});
        }
        console.log("OTP : ",otp);
        //(2)otp ko db me store karo
        const otpBody = await OTP.create({email,otp});
        console.log("OTP : ",otpBody);
        
        //(3)uske mail par otp send karo => done alreay by pre middleware in schema of otp.js
        //pre => OTP.create() se pahle run hoga
        return res.status(200).json({
            success:true,
            message:"OTP sent succesfully",
            otp
        });
    }
    catch(err){
        return res.status(500).json({
            success:false,
            message:err.message
        });
    }
    
};

//signUp
exports.signUp = async (req,res) =>{
    try{
        //fetch data from req body
        const {
            firstName,
            lastName,
            contactNumber,
            otp,
            email,
            password,
            confirmPassword,
            accountType
        } = req.body;

        //check if all data is entered by user
        if(!firstName || !lastName || !email || !otp || !password || !confirmPassword){
            return res.status(403).json({
                success:false,
                message:"Enter data in all fields"
            });
        }

        //match password and confirmPassword
        if(password !== confirmPassword){
            return res.status(400).json({
                success:false,
                message:"Confirm password is diffrent from password"
            });
        }

        //check if user already exist
        const userPresent = await User.findOne({email});
        if(userPresent){
            return res.status(400).json({
                success:false,
                message:"User already exist so not able to signIn"
            });
        }

        //find most recent otp
        const recentOtp = await OTP.find({email}).sort({ createdAt: -1 }).limit(1);;
        console.log(recentOtp);

        //validate otp
        if(recentOtp.length === 0){
            return res.status(400).json({
                success:false,
                message:"OTP not found"
            });
        }
        else if(otp !== recentOtp[0].otp){
            return res.status(400).json({
                success:false,
                message:"Invalid otp"
            });
        }

        //hash password
        const hashedPassword = await bcrypt.hash(password,10);

        //create user in db
        let approved = "";
		approved === "Instructor" ? (approved = false) : (approved = true);
        //profileDetail ki obj id chahiye additionalDetail me aur additionalDetail chahiye kyuki wo schema me he user ke
        const profileDetails = await Profile.create({
            gender:null,
            contactNumber:null,
            dateOfBirth:null,
            about:null
        });

        const user = await User.create({
            firstName,
            lastName,
            email,
            contactNumber,
            password:hashedPassword,
            accountType,
            approved,
            additionalDetails:profileDetails._id,
            image:`https://api.dicebear.com/5.x/initials/svg?seed=${firstName} ${lastName}`
        });

        return res.status(200).json({
            success:true,
            message:"Signed Up succesfully",
            user
        });

    }
    catch(err){
        return res.status(500).json({
            success:false,
            message:err.message
        });
    }
};

//login
exports.login = async (req,res) =>{
    try{
        //fetch data from req body
        const {email,password} = req.body;
        //validate data
        if(!email || !password){
            return res.status(403).json({
                success:false,
                message:"Enter data in all fields"
            });
        }
        //check if signed up or not
        const user = await User.findOne({email}).populate("additionalDetails");
        if(!user){
            return res.status(403).json({
                success:false,
                message:"please Sign up first"
            });
        }
        //if password matched create jwt token and cookie
        if(await bcrypt.compare(password,user.password)){
            const payload = {
                email:user.email,
                id : user._id,
                accountType:user.accountType
            }
            const token = jwt.sign(payload,process.env.JWT_SECRET,{
                expiresIn:"24h"
            });
            user.token = token;
            user.password = undefined;

            const options = {
                expires: new Date(Date.now() + 3*24*60*60*1000),
                httpOnly:true
            }
            res.cookie("token",token,options).status(200).json({
                success:true,
                token,
                user,
                message:"Logged in succesfully"
            })
        }
        else{
            return res.status(403).json({
                success:false,
                message:"Incorrect password"
            });
        }
    }
    catch(err){
        return res.status(403).json({
            success:false,
            message:err.message
        });
    }
};

//change password
exports.changePassword = async (req, res) => {
	try {
		// Get user data from req.user
		const userDetails = await User.findById(req.user.id);

		// Get old password, new password, and confirm new password from req.body
		const { oldPassword, newPassword} = req.body;

		// Validate old password
		const isPasswordMatch = await bcrypt.compare(
			oldPassword,
			userDetails.password
		);
		if (!isPasswordMatch) {
			// If old password does not match, return a 401 (Unauthorized) error
			return res
				.status(401)
				.json({ success: false, message: "The password is incorrect" });
		}

		// Match new password and confirm new password
		// if (newPassword !== confirmNewPassword) {
		// 	// If new password and confirm new password do not match, return a 400 (Bad Request) error
		// 	return res.status(400).json({
		// 		success: false,
		// 		message: "The password and confirm password does not match",
		// 	});
		// }

		// Update password
		const encryptedPassword = await bcrypt.hash(newPassword, 10);
		const updatedUserDetails = await User.findByIdAndUpdate(
			req.user.id,
			{ password: encryptedPassword },
			{ new: true }
		);

		// Send notification email
		try {
			const emailResponse = await mailSender(
				updatedUserDetails.email,
                "Password Changed",
				passwordUpdated(
					updatedUserDetails.email,
					updatedUserDetails.firstName
				)
			);
			console.log("Email sent successfully:", emailResponse.response);
		} catch (error) {
			// If there's an error sending the email, log the error and return a 500 (Internal Server Error) error
			console.error("Error occurred while sending email:", error);
			return res.status(500).json({
				success: false,
				message: "Error occurred while sending email",
				error: error.message,
			});
		}

		// Return success response
		return res
			.status(200)
			.json({ success: true, message: "Password updated successfully" });
	} catch (error) {
		// If there's an error updating the password, log the error and return a 500 (Internal Server Error) error
		console.error("Error occurred while updating password:", error);
		return res.status(500).json({
			success: false,
			message: "Error occurred while updating password",
			error: error.message,
		});
	}
};